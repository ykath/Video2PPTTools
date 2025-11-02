from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import AnyHttpUrl, BaseModel, Field


class SlideInfoModel(BaseModel):
    index: int = Field(..., ge=1)
    filename: str
    path: str
    timestamp_seconds: float = Field(..., ge=0.0)
    timestamp_text: str
    width: int = Field(..., ge=1)
    height: int = Field(..., ge=1)
    similarity: Optional[float] = Field(None, ge=0.0, le=1.0)


class VideoToPPTJobCreateRequest(BaseModel):
    url: AnyHttpUrl
    title: Optional[str] = None
    subtitle: Optional[str] = None
    similarity_threshold: float = Field(0.95, ge=0.0, le=1.0)
    min_interval_seconds: float = Field(2.0, ge=0.0)
    skip_first_seconds: float = Field(0.0, ge=0.0)
    fill_mode: bool = True
    image_format: str = Field("jpg", min_length=3, max_length=4)
    image_quality: int = Field(95, ge=10, le=100)
    job_id: Optional[str] = Field(
        None,
        max_length=64,
        description="Optional custom job identifier",
    )
    extra_download_args: Optional[List[str]] = Field(
        None,
        description="Additional command line arguments forwarded to BBDown",
    )
    file_pattern: Optional[str] = Field(
        None,
        description="Custom BBDown --file-pattern override",
    )


class VideoToPPTJobSummary(BaseModel):
    id: int
    job_id: str
    url: AnyHttpUrl
    title: Optional[str] = None
    subtitle: Optional[str] = None
    status: str
    slide_count: Optional[int] = None
    image_format: Optional[str] = None
    image_quality: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    ppt_path: Optional[str] = None


class VideoToPPTJobDetail(VideoToPPTJobSummary):
    similarity_threshold: Optional[float] = None
    min_interval_seconds: Optional[float] = None
    skip_first_seconds: Optional[float] = None
    fill_mode: Optional[bool] = None
    extra_download_args: Optional[List[str]] = None
    file_pattern: Optional[str] = None
    video_path: Optional[str] = None
    video_files: Optional[List[str]] = None
    job_dir: Optional[str] = None
    slides_json_path: Optional[str] = None
    screenshots_dir: Optional[str] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    command: Optional[List[str]] = None
    video_duration_seconds: Optional[float] = None
    fps: Optional[float] = None
    slides: Optional[List[SlideInfoModel]] = None


class VideoToPPTJobListResponse(BaseModel):
    total: int
    items: List[VideoToPPTJobSummary]
