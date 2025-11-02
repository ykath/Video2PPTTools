from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional


@dataclass
class VideoDownloadResult:
    url: str
    video_path: Path
    video_paths: List[Path]
    output_dir: Path
    command: List[str]
    stdout: str
    stderr: str
    started_at: datetime
    completed_at: datetime
    video_title: Optional[str] = None  # 从BBDown输出提取的视频标题

    @property
    def filename(self) -> str:
        return self.video_path.name

    @property
    def stem(self) -> str:
        return self.video_path.stem


@dataclass
class SlideInfo:
    index: int
    filename: str
    path: Path
    timestamp_seconds: float
    timestamp_text: str
    width: int
    height: int
    similarity: Optional[float] = None


@dataclass
class SlideExtractionResult:
    slides: List[SlideInfo]
    screenshots_dir: Path
    video_path: Path
    fps: float
    total_frames: int
    duration_seconds: float
    json_path: Optional[Path]


@dataclass
class PPTBuildResult:
    ppt_path: Path
    slide_count: int


@dataclass
class PipelineResult:
    job_id: str
    job_dir: Path
    video_url: str
    download: VideoDownloadResult
    slides: SlideExtractionResult
    ppt: PPTBuildResult
