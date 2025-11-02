from __future__ import annotations

import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Sequence

from .errors import VideoDownloadError
from .models import VideoDownloadResult

LOGGER = logging.getLogger(__name__)


class YtDlpDownloader:
    """Wrapper around yt-dlp for downloading YouTube videos."""

    VIDEO_EXTENSIONS = (".mp4", ".mkv", ".webm", ".m4a", ".flv", ".avi")

    def __init__(self, executable: Path, default_args: Sequence[str] | None = None) -> None:
        self.executable = Path(executable).resolve()
        self.default_args = list(default_args or [])

        if not self.executable.exists():
            raise FileNotFoundError(f"yt-dlp executable not found: {self.executable}")
        
        if not self.executable.is_file():
            raise FileNotFoundError(f"yt-dlp path is not a file: {self.executable}")

    def download(
        self,
        url: str,
        output_dir: Path,
        file_pattern: str | None = None,
        extra_args: Sequence[str] | None = None,
    ) -> VideoDownloadResult:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # 先获取视频元数据（包括标题）
        video_title = self._fetch_video_metadata(url)
        LOGGER.info("Fetched video title: %s", video_title)

        # yt-dlp输出模板 - 使用 %(title)s 确保文件名包含标题
        # 如果提供了file_pattern，使用它；否则使用 "%(title)s.%(ext)s"
        if file_pattern:
            output_template = str(output_dir / f"{file_pattern}.%(ext)s")
        else:
            # 使用标题作为文件名，yt-dlp会自动清理非法字符
            output_template = str(output_dir / "%(title)s.%(ext)s")
        
        command: List[str] = [
            str(self.executable),
            url,
            "-o", output_template,
            "--no-playlist",  # 不下载播放列表
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",  # 优先MP4
            "--print", "after_move:filepath",  # 打印最终文件路径
        ]
        
        # 添加默认参数
        command.extend(self.default_args)
        
        # 添加额外参数
        if extra_args:
            command.extend(extra_args)

        started_at = datetime.utcnow()
        LOGGER.info("Downloading video via yt-dlp: %s", url)
        LOGGER.info("yt-dlp command: %s", " ".join(command))
        
        try:
            import platform
            kwargs = {
                "capture_output": True,
                "text": True,
                "encoding": "utf-8",
                "errors": "ignore",
                "check": False,
            }
            
            # Windows下添加CREATE_NO_WINDOW标志
            if platform.system() == "Windows":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            
            completed = subprocess.run(command, **kwargs)
        except (OSError, PermissionError) as exc:
            LOGGER.error("Failed to start yt-dlp. Executable: %s, Command: %s, Error: %s", 
                        self.executable, command, exc)
            raise VideoDownloadError(f"Failed to start yt-dlp: {exc}") from exc

        completed_at = datetime.utcnow()

        stdout = completed.stdout or ""
        stderr = completed.stderr or ""

        # 记录完整的输出信息
        LOGGER.info("yt-dlp stdout:\n%s", stdout)
        if stderr:
            LOGGER.warning("yt-dlp stderr:\n%s", stderr)
        LOGGER.info("yt-dlp exit code: %s", completed.returncode)

        # 尝试定位视频文件
        video_paths = self._locate_video_files(output_dir)
        
        # 即使yt-dlp返回错误码，只要找到了有效的视频文件就继续
        if not video_paths:
            if completed.returncode != 0:
                LOGGER.error("yt-dlp failed (code=%s) and no video file found", completed.returncode)
                raise VideoDownloadError(
                    f"yt-dlp exited with code {completed.returncode}. stderr: {stderr.strip()}"
                )
            else:
                raise VideoDownloadError("Download finished but no video file was found.")
        
        # 如果找到了视频文件但yt-dlp返回了错误码，记录警告但继续处理
        if completed.returncode != 0:
            LOGGER.warning("yt-dlp returned error code %s but video file was found, continuing...", 
                          completed.returncode)

        primary_video_path = video_paths[0]
        LOGGER.info("Video downloaded: %s", primary_video_path)

        return VideoDownloadResult(
            url=url,
            video_path=primary_video_path,
            video_paths=video_paths,
            output_dir=output_dir,
            command=command,
            stdout=stdout,
            stderr=stderr,
            started_at=started_at,
            completed_at=completed_at,
            video_title=video_title,  # 使用预先获取的标题
        )

    def _locate_video_files(self, directory: Path) -> List[Path]:
        candidates: List[Path] = []
        for path in directory.rglob("*"):
            if path.is_file() and path.suffix.lower() in self.VIDEO_EXTENSIONS:
                # 排除0字节文件（下载失败或未完成）
                if path.stat().st_size > 0:
                    candidates.append(path)

        if not candidates:
            LOGGER.warning("No valid video files found in %s", directory)
            return []

        # 按文件大小排序，选择最大的文件（通常是主视频）
        candidates.sort(key=lambda p: p.stat().st_size, reverse=True)
        LOGGER.info("Found %d video file(s), selected: %s (size: %d bytes)", 
                   len(candidates), candidates[0].name, candidates[0].stat().st_size)
        return candidates

    def _fetch_video_metadata(self, url: str) -> str | None:
        """
        使用 --print-json 获取视频元数据
        
        Args:
            url: 视频URL
            
        Returns:
            视频标题，如果获取失败则返回None
        """
        try:
            import json
            import platform
            
            # 构建获取元数据的命令
            command = [
                str(self.executable),
                url,
                "--skip-download",  # 不下载视频
                "--print-json",  # 输出JSON格式的元数据
                "--no-playlist",  # 不处理播放列表
            ]
            
            kwargs = {
                "capture_output": True,
                "text": True,
                "encoding": "utf-8",
                "errors": "ignore",
                "check": False,
                "timeout": 30,  # 30秒超时
            }
            
            if platform.system() == "Windows":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            
            LOGGER.debug("Fetching metadata with command: %s", " ".join(command))
            result = subprocess.run(command, **kwargs)
            
            if result.returncode == 0 and result.stdout:
                # 解析JSON输出
                try:
                    metadata = json.loads(result.stdout)
                    title = metadata.get("title")
                    if title:
                        LOGGER.info("Successfully fetched video title from metadata: %s", title)
                        return title
                except json.JSONDecodeError as e:
                    LOGGER.warning("Failed to parse JSON metadata: %s", e)
            else:
                LOGGER.warning("Failed to fetch metadata (code=%s): %s", result.returncode, result.stderr)
                
        except Exception as e:
            LOGGER.warning("Error fetching video metadata: %s", e)
        
        return None

