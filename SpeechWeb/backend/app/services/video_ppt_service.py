from __future__ import annotations

import json
import logging
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import BackgroundTasks

from Src.config import BBDOWN_EXECUTABLE, VIDEO_TO_PPT_ROOT, YTDLP_EXECUTABLE
from Src.video_to_ppt import PipelineConfig, PipelineOptions, VideoToPPTError, VideoToPPTPipeline

from ..core.db import get_database
from ..models.ppt import (
    SlideInfoModel,
    VideoToPPTJobCreateRequest,
    VideoToPPTJobDetail,
    VideoToPPTJobListResponse,
    VideoToPPTJobSummary,
)

LOGGER = logging.getLogger(__name__)

# 使用最简单的参数，避免版本兼容问题
DEFAULT_BBDOWN_ARGS: List[str] = []


def resolve_relative_path(path_str: Optional[str]) -> Optional[Path]:
    """
    将相对路径转换为绝对路径
    如果已经是绝对路径，直接返回
    如果是None，返回None
    """
    if not path_str:
        return None
    
    from Src.config import BASE_DIR
    path = Path(path_str)
    if not path.is_absolute():
        path = BASE_DIR / path
    return path


class VideoPPTServiceError(RuntimeError):
    """Raised when the video-to-PPT workflow fails."""


@lru_cache()
def get_pipeline() -> VideoToPPTPipeline:
    config = PipelineConfig(
        bbdown_executable=BBDOWN_EXECUTABLE,
        workspace_root=VIDEO_TO_PPT_ROOT,
        ytdlp_executable=YTDLP_EXECUTABLE,  # 添加yt-dlp配置
        default_bbdown_args=DEFAULT_BBDOWN_ARGS,
        default_ytdlp_args=[],  # yt-dlp默认参数（如需要可配置）
    )
    return VideoToPPTPipeline(config=config)


def _generate_job_id() -> str:
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    suffix = uuid4().hex[:6]
    return f"ppt-{timestamp}-{suffix}"


def _to_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        LOGGER.debug("Failed to parse datetime string: %s", value)
        return None


def _decode_extra_args(value: Optional[str]) -> Optional[List[str]]:
    if not value:
        return None
    try:
        data = json.loads(value)
        if isinstance(data, list):
            return [str(item) for item in data]
    except json.JSONDecodeError:
        LOGGER.warning("Failed to decode extra args JSON: %s", value)
    return None


def _decode_command(value: Optional[str]) -> Optional[List[str]]:
    if not value:
        return None
    try:
        data = json.loads(value)
        if isinstance(data, list):
            return [str(item) for item in data]
    except json.JSONDecodeError:
        LOGGER.warning("Failed to decode command JSON: %s", value)
    return None


def _decode_video_files(value: Optional[str]) -> Optional[List[str]]:
    if not value:
        return None
    try:
        data = json.loads(value)
        if isinstance(data, list):
            return [str(item) for item in data]
    except json.JSONDecodeError:
        LOGGER.warning("Failed to decode video files JSON: %s", value)
    return None


def _row_to_summary(row: Dict[str, Any]) -> VideoToPPTJobSummary:
    return VideoToPPTJobSummary(
        id=row["id"],
        job_id=row["job_id"],
        url=row["url"],
        title=row.get("title"),
        subtitle=row.get("subtitle"),
        status=row.get("status", "pending"),
        slide_count=row.get("slide_count"),
        image_format=row.get("image_format"),
        image_quality=row.get("image_quality"),
        created_at=_to_datetime(row.get("created_at")),
        updated_at=_to_datetime(row.get("updated_at")),
        started_at=_to_datetime(row.get("started_at")),
        completed_at=_to_datetime(row.get("completed_at")),
        error_message=row.get("error_message"),
        ppt_path=row.get("ppt_path"),
    )


def _load_slides(slides_json_path: Optional[str]) -> Optional[List[SlideInfoModel]]:
    path = resolve_relative_path(slides_json_path)
    if not path or not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Failed to read slides JSON %s: %s", path, exc)
        return None
    slides = data.get("slides")
    if not isinstance(slides, list):
        return None
    items: List[SlideInfoModel] = []
    for slide in slides:
        try:
            items.append(
                SlideInfoModel(
                    index=slide.get("index"),
                    filename=slide.get("filename"),
                    path=slide.get("path"),
                    timestamp_seconds=slide.get("timestamp_seconds", 0.0),
                    timestamp_text=slide.get("timestamp", ""),
                    width=slide.get("width", 0),
                    height=slide.get("height", 0),
                    similarity=slide.get("similarity"),
                )
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.debug("Failed to parse slide entry %s: %s", slide, exc)
    return items or None


def _row_to_detail(row: Dict[str, Any]) -> VideoToPPTJobDetail:
    summary = _row_to_summary(row)
    slides = _load_slides(row.get("slides_json_path")) if summary.status == "completed" else None
    return VideoToPPTJobDetail(
        **summary.dict(),
        similarity_threshold=row.get("similarity_threshold"),
        min_interval_seconds=row.get("min_interval_seconds"),
        skip_first_seconds=row.get("skip_first_seconds"),
        fill_mode=bool(row.get("fill_mode", 1)),
        extra_download_args=_decode_extra_args(row.get("extra_download_args")),
        file_pattern=row.get("file_pattern"),
        video_path=row.get("video_path"),
        job_dir=row.get("job_dir"),
        slides_json_path=row.get("slides_json_path"),
        screenshots_dir=row.get("screenshots_dir"),
        stdout=row.get("stdout"),
        stderr=row.get("stderr"),
        command=_decode_command(row.get("command")),
        video_duration_seconds=row.get("video_duration_seconds"),
        fps=row.get("fps"),
        video_files=_decode_video_files(row.get("video_files")),
        slides=slides,
    )


def process_all_pending_jobs() -> Dict[str, Any]:
    """批量处理所有pending任务"""
    with get_database() as db:
        cursor = db.connection.cursor()
        row = cursor.execute("SELECT COUNT(*) as count FROM video_ppt_jobs WHERE status = 'pending'").fetchone()
        pending_count = row["count"] if row else 0
        
        if pending_count == 0:
            return {"message": "No pending jobs to process", "count": 0}
        
        # 检查是否有运行中的任务
        row = cursor.execute("SELECT COUNT(*) as count FROM video_ppt_jobs WHERE status = 'running'").fetchone()
        has_running = row["count"] > 0 if row else False
        
        if has_running:
            return {"message": f"{pending_count} jobs already queued, will process automatically", "count": pending_count}
        
        # 启动第一个pending任务
        _process_next_pending_job()
        
        return {"message": f"Started processing queue ({pending_count} pending jobs)", "count": pending_count}


def reprocess_job(job_id: str) -> VideoToPPTJobDetail:
    """重新处理单个任务"""
    with get_database() as db:
        job_data = db.get_video_ppt_job_by_job_id(job_id)
        if not job_data:
            raise VideoPPTServiceError(f"Job not found: {job_id}")
        
        # 检查任务状态
        if job_data["status"] == "running":
            raise VideoPPTServiceError(f"Job is already running: {job_id}")
        
        # 重置任务状态为pending
        db.update_video_ppt_job(
            job_id,
            status="pending",
            started_at=None,
            completed_at=None,
            error_message=None,
            ppt_path=None,
            video_path=None,
            job_dir=None,
        )
        
        # 检查是否有运行中的任务
        cursor = db.connection.cursor()
        row = cursor.execute("SELECT COUNT(*) as count FROM video_ppt_jobs WHERE status = 'running'").fetchone()
        has_running = row["count"] > 0 if row else False
        
        if not has_running:
            # 没有运行中的任务，立即启动
            _process_next_pending_job()
        
        # 返回更新后的任务详情
        updated_job = db.get_video_ppt_job_by_job_id(job_id)
        return _row_to_detail(updated_job)


def list_jobs(limit: Optional[int] = None) -> VideoToPPTJobListResponse:
    LOGGER.debug("Listing video-to-PPT jobs limit=%s", limit)
    with get_database() as db:
        rows = db.list_video_ppt_jobs(limit=limit)
    items = [_row_to_summary(row) for row in rows]
    return VideoToPPTJobListResponse(total=len(items), items=items)


def list_completed_jobs_for_browsing(page: int = 1, page_size: int = 20, search_term: Optional[str] = None) -> Dict[str, Any]:
    """获取已完成任务列表用于浏览页面展示"""
    with get_database() as db:
        cursor = db.connection.cursor()
        
        # 构建查询条件
        where_clause = "WHERE status = 'completed'"
        params = []
        
        if search_term:
            where_clause += " AND (title LIKE ? OR subtitle LIKE ? OR url LIKE ?)"
            search_pattern = f"%{search_term}%"
            params.extend([search_pattern, search_pattern, search_pattern])
        
        # 获取总数
        count_query = f"SELECT COUNT(*) as total FROM video_ppt_jobs {where_clause}"
        total = cursor.execute(count_query, params).fetchone()["total"]
        
        # 分页查询
        offset = (page - 1) * page_size
        list_query = f"""
            SELECT * FROM video_ppt_jobs {where_clause}
            ORDER BY completed_at DESC
            LIMIT ? OFFSET ?
        """
        rows = cursor.execute(list_query, params + [page_size, offset]).fetchall()
        
        items = [_row_to_detail(dict(row)) for row in rows]
        
        return {
            "total": total,
            "items": items,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
        }


def get_job(job_id: str) -> Optional[VideoToPPTJobDetail]:
    with get_database() as db:
        row = db.get_video_ppt_job_by_job_id(job_id)
    if not row:
        return None
    return _row_to_detail(row)


def create_job(payload: VideoToPPTJobCreateRequest, background_tasks: Optional[BackgroundTasks] = None) -> VideoToPPTJobDetail:
    job_id = payload.job_id or _generate_job_id()
    LOGGER.info("Creating video-to-PPT job job_id=%s url=%s", job_id, payload.url)
    
    with get_database() as db:
        existing = db.get_video_ppt_job_by_job_id(job_id)
        if existing:
            raise VideoPPTServiceError(f"Job ID already exists: {job_id}")
        
        # 检查URL是否已存在
        cursor = db.connection.cursor()
        existing_url = cursor.execute(
            "SELECT job_id, status FROM video_ppt_jobs WHERE url = ? ORDER BY created_at DESC LIMIT 1",
            (str(payload.url),)
        ).fetchone()
        if existing_url:
            existing_job_id = existing_url["job_id"]
            existing_status = existing_url["status"]
            LOGGER.warning("URL already exists: job_id=%s status=%s", existing_job_id, existing_status)
            raise VideoPPTServiceError(
                f"此视频URL已存在任务（任务ID: {existing_job_id}，状态: {existing_status}）"
            )
        
        # 检查是否有运行中的任务
        cursor = db.connection.cursor()
        running_jobs = cursor.execute("SELECT COUNT(*) as count FROM video_ppt_jobs WHERE status = 'running'").fetchone()
        has_running_job = running_jobs["count"] > 0 if running_jobs else False
        
        row = db.insert_video_ppt_job(
            {
                "job_id": job_id,
                "url": str(payload.url),
                "title": payload.title,
                "subtitle": payload.subtitle,
                "similarity_threshold": payload.similarity_threshold,
                "min_interval_seconds": payload.min_interval_seconds,
                "skip_first_seconds": payload.skip_first_seconds,
                "fill_mode": payload.fill_mode,
                "image_format": payload.image_format,
                "image_quality": payload.image_quality,
                "extra_download_args": payload.extra_download_args,
                "file_pattern": payload.file_pattern,
                "status": "pending",
            }
        )

    job_detail = _row_to_detail(row)
    task_payload = payload.dict()
    task_payload["job_id"] = job_id
    
    # 如果有运行中的任务，不立即执行，等待队列处理
    if has_running_job:
        LOGGER.info("Job queued (job_id=%s), waiting for running job to complete", job_id)
    elif background_tasks is not None:
        LOGGER.debug("Queueing background task for job_id=%s", job_id)
        background_tasks.add_task(_run_job_task, task_payload)
    else:
        LOGGER.debug("Running job synchronously job_id=%s", job_id)
        _run_job_task(task_payload)
    
    return job_detail


def _process_next_pending_job() -> None:
    """检查并处理下一个待处理的任务"""
    with get_database() as db:
        # 获取最早创建的pending任务
        cursor = db.connection.cursor()
        cursor.execute("SELECT * FROM video_ppt_jobs WHERE status = 'pending' ORDER BY created_at ASC LIMIT 1")
        row = cursor.fetchone()
        if not row:
            LOGGER.info("No pending jobs in queue")
            return
        
        job_data = dict(row)
        job_id = job_data["job_id"]
        LOGGER.info("Found pending job in queue: %s", job_id)
        
        # 构建payload
        payload_dict = {
            "job_id": job_id,
            "url": job_data["url"],
            "title": job_data.get("title"),
            "subtitle": job_data.get("subtitle"),
            "similarity_threshold": job_data.get("similarity_threshold", 0.95),
            "min_interval_seconds": job_data.get("min_interval_seconds", 2.0),
            "skip_first_seconds": job_data.get("skip_first_seconds", 0.0),
            "fill_mode": job_data.get("fill_mode", True),
            "image_format": job_data.get("image_format", "jpg"),
            "image_quality": job_data.get("image_quality", 95),
            "extra_download_args": job_data.get("extra_download_args"),
            "file_pattern": job_data.get("file_pattern"),
        }
        
        # 在后台任务中执行
        import threading
        thread = threading.Thread(target=_run_job_task, args=(payload_dict,))
        thread.daemon = True
        thread.start()


def _run_job_task(payload_dict: Dict[str, Any]) -> None:
    job_id = payload_dict["job_id"]
    LOGGER.info("Starting background job %s for %s", job_id, payload_dict.get("url"))
    try:
        pipeline = get_pipeline()
    except FileNotFoundError as exc:
        LOGGER.error("BBDown executable not configured: %s", exc)
        with get_database() as db:
            db.mark_video_ppt_job_failed(job_id, f"BBDown executable not configured: {exc}")
        return

    options = PipelineOptions(
        similarity_threshold=payload_dict.get("similarity_threshold", 0.95),
        min_interval_seconds=payload_dict.get("min_interval_seconds", 2.0),
        skip_first_seconds=payload_dict.get("skip_first_seconds", 0.0),
        fill_mode=payload_dict.get("fill_mode", True),
        image_format=payload_dict.get("image_format", "jpg"),
        image_quality=payload_dict.get("image_quality", 95),
        title=payload_dict.get("title"),
        subtitle=payload_dict.get("subtitle"),
        job_id=payload_dict.get("job_id"),
        extra_download_args=payload_dict.get("extra_download_args"),
        file_pattern=payload_dict.get("file_pattern"),
    )

    with get_database() as db:
        db.mark_video_ppt_job_started(job_id)

    try:
        result = pipeline.run(str(payload_dict["url"]), options=options)
    except VideoToPPTError as exc:
        LOGGER.error("Video-to-PPT pipeline failed (job=%s): %s", job_id, exc)
        with get_database() as db:
            db.mark_video_ppt_job_failed(job_id, str(exc))
        return
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Unexpected pipeline failure (job=%s): %s", job_id, exc)
        with get_database() as db:
            db.mark_video_ppt_job_failed(job_id, f"Unexpected error: {exc}")
        return

    # 如果用户没有提供title/subtitle，从下载结果中提取
    extracted_title = result.download.video_title
    final_title = payload_dict.get("title") or extracted_title
    final_subtitle = payload_dict.get("subtitle") or extracted_title
    
    # 如果提取到了标题且用户未提供，更新数据库
    if extracted_title and (not payload_dict.get("title") or not payload_dict.get("subtitle")):
        LOGGER.info("Updating job title/subtitle with extracted title: %s", extracted_title)
        with get_database() as db:
            update_data = {}
            if not payload_dict.get("title"):
                update_data["title"] = final_title
            if not payload_dict.get("subtitle"):
                update_data["subtitle"] = final_subtitle
            if update_data:
                # 使用SQL直接更新
                cursor = db.connection.cursor()
                cursor.execute(
                    "UPDATE video_ppt_jobs SET title = COALESCE(?, title), subtitle = COALESCE(?, subtitle) WHERE job_id = ?",
                    (update_data.get("title"), update_data.get("subtitle"), job_id)
                )
                db.connection.commit()

    # 将绝对路径转换为相对路径（相对于部署根目录）
    from Src.config import BASE_DIR
    
    def to_relative_path(abs_path: Path) -> str:
        """将绝对路径转换为相对路径"""
        try:
            return str(abs_path.relative_to(BASE_DIR)).replace("\\", "/")
        except (ValueError, AttributeError):
            # 如果无法转换为相对路径，返回原路径
            return str(abs_path).replace("\\", "/")
    
    result_payload = {
        "job_dir": to_relative_path(result.job_dir),
        "video_path": to_relative_path(result.download.video_path),
        "video_files": [to_relative_path(path) for path in result.download.video_paths],
        "ppt_path": to_relative_path(result.ppt.ppt_path),
        "slides_json_path": to_relative_path(result.slides.json_path) if result.slides.json_path else None,
        "screenshots_dir": to_relative_path(result.slides.screenshots_dir),
        "command": result.download.command,
        "stdout": result.download.stdout,
        "stderr": result.download.stderr,
        "video_duration_seconds": result.slides.duration_seconds,
        "fps": result.slides.fps,
        "slide_count": result.ppt.slide_count,
    }

    with get_database() as db:
        db.mark_video_ppt_job_completed(job_id, result_payload)
    LOGGER.info("Video-to-PPT job completed: %s", job_id)
    
    # 任务完成后，处理下一个等待的任务
    _process_next_pending_job()
