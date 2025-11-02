from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Sequence
from uuid import uuid4

from .downloader import BBDownDownloader
from .errors import PPTBuildError, SlideExtractionError, VideoDownloadError, VideoToPPTError
from .extractor import SlideExtractor
from .models import PipelineResult, PPTBuildResult, SlideExtractionResult, VideoDownloadResult
from .ppt_builder import PPTBuilder
from .url_detector import VideoSource, detect_video_source
from .ytdlp_downloader import YtDlpDownloader

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineConfig:
    bbdown_executable: Path
    workspace_root: Path
    ytdlp_executable: Path | None = None  # 可选的yt-dlp路径
    default_bbdown_args: Sequence[str] = field(default_factory=tuple)
    default_ytdlp_args: Sequence[str] = field(default_factory=tuple)
    keep_download_video: bool = True


@dataclass
class PipelineOptions:
    similarity_threshold: float = 0.95
    min_interval_seconds: float = 2.0
    skip_first_seconds: float = 0.0
    fill_mode: bool = True
    image_format: str = "jpg"
    image_quality: int = 95
    title: str | None = None
    subtitle: str | None = None
    job_id: str | None = None
    extra_download_args: Sequence[str] | None = None
    file_pattern: str | None = None


class VideoToPPTPipeline:
    """High-level orchestrator that converts bilibili videos into PPT decks."""

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.config.workspace_root.mkdir(parents=True, exist_ok=True)
        
        # 初始化B站下载器
        self._bbdown_downloader = BBDownDownloader(
            executable=config.bbdown_executable,
            default_args=config.default_bbdown_args,
        )
        
        # 初始化YouTube下载器（如果配置了）
        self._ytdlp_downloader = None
        if config.ytdlp_executable and config.ytdlp_executable.exists():
            try:
                self._ytdlp_downloader = YtDlpDownloader(
                    executable=config.ytdlp_executable,
                    default_args=config.default_ytdlp_args,
                )
                LOGGER.info("yt-dlp downloader initialized: %s", config.ytdlp_executable)
            except FileNotFoundError as e:
                LOGGER.warning("Failed to initialize yt-dlp: %s", e)

    def run(self, url: str, options: PipelineOptions | None = None) -> PipelineResult:
        if not url:
            raise VideoToPPTError("Video URL is required.")

        opts = options or PipelineOptions()
        job_id = opts.job_id or self._generate_job_id()
        job_dir = self.config.workspace_root / job_id
        download_dir = job_dir / "download"
        slides_dir = job_dir / "slides"
        images_dir = slides_dir / "images"
        ppt_dir = job_dir / "ppt"

        for path in [download_dir, images_dir, ppt_dir]:
            path.mkdir(parents=True, exist_ok=True)

        LOGGER.info("Starting video-to-PPT pipeline (job=%s)", job_id)

        try:
            download_result = self._download_video(
                url=url,
                download_dir=download_dir,
                file_pattern=opts.file_pattern or job_id,
                extra_args=opts.extra_download_args,
            )
            
            # 如果用户未提供title/subtitle，使用从BBDown提取的标题
            if download_result.video_title:
                if not opts.title:
                    opts.title = download_result.video_title
                    LOGGER.info("Using extracted video title for PPT: %s", opts.title)
                if not opts.subtitle:
                    opts.subtitle = download_result.video_title
                    LOGGER.info("Using extracted video title for PPT subtitle: %s", opts.subtitle)
            
            slides_result = self._extract_slides(
                download_result=download_result,
                images_dir=images_dir,
                slides_json_path=slides_dir / "slides.json",
                options=opts,
            )
            ppt_result = self._build_ppt(
                slides_result=slides_result,
                ppt_dir=ppt_dir,
                options=opts,
            )
        except (VideoToPPTError, VideoDownloadError, SlideExtractionError, PPTBuildError):
            # Pass through typed pipeline errors
            raise
        except Exception as exc:
            LOGGER.exception("Pipeline failed unexpectedly: %s", exc)
            raise VideoToPPTError(f"Unexpected pipeline error: {exc}") from exc
        finally:
            if not self.config.keep_download_video:
                self._cleanup_download(download_dir)

        return PipelineResult(
            job_id=job_id,
            job_dir=job_dir,
            video_url=url,
            download=download_result,
            slides=slides_result,
            ppt=ppt_result,
        )

    def _download_video(
        self,
        url: str,
        download_dir: Path,
        file_pattern: str,
        extra_args: Sequence[str] | None,
    ) -> VideoDownloadResult:
        # 检测视频来源并选择合适的下载器
        source = detect_video_source(url)
        LOGGER.info("Detected video source: %s for URL: %s", source.value, url)
        
        try:
            if source == VideoSource.YOUTUBE:
                if not self._ytdlp_downloader:
                    raise VideoDownloadError(
                        "YouTube视频需要yt-dlp，但未配置或初始化失败。"
                        "请配置YTDLP_EXECUTABLE环境变量或将yt-dlp.exe放在项目根目录。"
                    )
                LOGGER.info("Using yt-dlp downloader for YouTube video")
                return self._ytdlp_downloader.download(
                    url=url,
                    output_dir=download_dir,
                    file_pattern=file_pattern,
                    extra_args=extra_args,
                )
            elif source == VideoSource.BILIBILI:
                LOGGER.info("Using BBDown downloader for Bilibili video")
                return self._bbdown_downloader.download(
                    url=url,
                    output_dir=download_dir,
                    file_pattern=file_pattern,
                    extra_args=extra_args,
                )
            else:
                # 未知来源，尝试用BBDown（向后兼容）
                LOGGER.warning("Unknown video source, trying BBDown")
                return self._bbdown_downloader.download(
                    url=url,
                    output_dir=download_dir,
                    file_pattern=file_pattern,
                    extra_args=extra_args,
                )
        except FileNotFoundError as exc:
            raise VideoToPPTError(str(exc)) from exc
        except VideoDownloadError:
            raise
        except Exception as exc:
            raise VideoDownloadError(f"Failed to download video: {exc}") from exc

    def _extract_slides(
        self,
        download_result: VideoDownloadResult,
        images_dir: Path,
        slides_json_path: Path,
        options: PipelineOptions,
    ) -> SlideExtractionResult:
        extractor = SlideExtractor(
            video_path=download_result.video_path,
            output_dir=images_dir,
            similarity_threshold=options.similarity_threshold,
            min_interval_seconds=options.min_interval_seconds,
            skip_first_seconds=options.skip_first_seconds,
            image_format=options.image_format,
            image_quality=options.image_quality,
        )
        try:
            return extractor.extract(json_path=slides_json_path)
        except SlideExtractionError:
            raise
        except Exception as exc:
            raise SlideExtractionError(f"Failed to extract slides: {exc}") from exc

    def _build_ppt(
        self,
        slides_result: SlideExtractionResult,
        ppt_dir: Path,
        options: PipelineOptions,
    ) -> PPTBuildResult:
        title = options.title or slides_result.video_path.stem
        subtitle = options.subtitle
        ppt_filename = self._safe_filename(title, suffix=".pptx")
        ppt_path = ppt_dir / ppt_filename

        builder = PPTBuilder(fill_mode=options.fill_mode)
        try:
            return builder.build(
                slides=slides_result.slides,
                output_path=ppt_path,
                title=title,
                subtitle=subtitle,
            )
        except PPTBuildError:
            raise
        except Exception as exc:
            raise PPTBuildError(f"Failed to build PPT: {exc}") from exc

    @staticmethod
    def _generate_job_id() -> str:
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        random_suffix = uuid4().hex[:6]
        return f"{timestamp}-{random_suffix}"

    @staticmethod
    def _safe_filename(name: str, suffix: str) -> str:
        sanitized = re.sub(r'[\\/:*?"<>|]', "_", name).strip("_")
        if not sanitized:
            sanitized = "output"
        return f"{sanitized}{suffix}"

    def _cleanup_download(self, download_dir: Path) -> None:
        for path in sorted(download_dir.glob("**/*"), reverse=True):
            try:
                if path.is_file():
                    path.unlink(missing_ok=True)
                elif path.is_dir():
                    path.rmdir()
            except OSError:
                LOGGER.debug("Skip cleanup for %s", path)
