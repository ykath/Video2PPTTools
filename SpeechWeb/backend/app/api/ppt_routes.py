from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse

from ..models.ppt import (
    VideoToPPTJobCreateRequest,
    VideoToPPTJobDetail,
    VideoToPPTJobListResponse,
)
from ..services.video_ppt_service import (
    VideoPPTServiceError,
    create_job,
    get_job,
    list_completed_jobs_for_browsing,
    list_jobs,
    process_all_pending_jobs,
    reprocess_job,
)

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/video-to-ppt", tags=["video-to-ppt"])


@router.post("/jobs", response_model=VideoToPPTJobDetail, name="create_video_ppt_job")
def create_video_ppt_job_endpoint(
    payload: VideoToPPTJobCreateRequest,
    background_tasks: BackgroundTasks,
) -> VideoToPPTJobDetail:
    LOGGER.info("API create_video_ppt_job called url=%s job_id=%s", payload.url, payload.job_id)
    try:
        job = create_job(payload, background_tasks=background_tasks)
        LOGGER.info("Video-to-PPT job accepted job_id=%s status=%s", job.job_id, job.status)
        return job
    except VideoPPTServiceError as exc:
        LOGGER.error("Failed to create video-to-PPT job: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/jobs", response_model=VideoToPPTJobListResponse, name="list_video_ppt_jobs")
def list_video_ppt_jobs_endpoint(limit: Optional[int] = Query(default=None, ge=1, le=200)) -> VideoToPPTJobListResponse:
    LOGGER.debug("API list_video_ppt_jobs called limit=%s", limit)
    return list_jobs(limit=limit)


@router.get("/jobs/{job_id}", response_model=VideoToPPTJobDetail, name="get_video_ppt_job")
def get_video_ppt_job_endpoint(job_id: str) -> VideoToPPTJobDetail:
    LOGGER.debug("API get_video_ppt_job called job_id=%s", job_id)
    job = get_job(job_id)
    if not job:
        LOGGER.warning("Video-to-PPT job not found job_id=%s", job_id)
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/jobs/process-queue", name="process_all_pending_jobs")
def process_all_pending_jobs_endpoint():
    """批量处理所有pending任务"""
    LOGGER.info("API process_all_pending_jobs called")
    try:
        result = process_all_pending_jobs()
        return result
    except VideoPPTServiceError as exc:
        LOGGER.error("Failed to process pending jobs: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/reprocess", response_model=VideoToPPTJobDetail, name="reprocess_job")
def reprocess_job_endpoint(job_id: str) -> VideoToPPTJobDetail:
    """重新处理单个任务"""
    LOGGER.info("API reprocess_job called job_id=%s", job_id)
    try:
        job = reprocess_job(job_id)
        return job
    except VideoPPTServiceError as exc:
        LOGGER.error("Failed to reprocess job: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/jobs/{job_id}/download", name="download_ppt")
def download_ppt_endpoint(job_id: str):
    """下载PPT文件"""
    LOGGER.info("API download_ppt called job_id=%s", job_id)
    job = get_job(job_id)
    if not job:
        LOGGER.warning("Job not found job_id=%s", job_id)
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.status != "completed":
        raise HTTPException(status_code=400, detail=f"Job is not completed (status: {job.status})")
    
    if not job.ppt_path:
        raise HTTPException(status_code=404, detail="PPT file not found")
    
    from ..services.video_ppt_service import resolve_relative_path
    
    # 处理相对路径：如果是相对路径，转换为绝对路径
    ppt_file = resolve_relative_path(job.ppt_path)
    if not ppt_file or not ppt_file.exists():
        raise HTTPException(status_code=404, detail="PPT file does not exist on disk")
    
    # 使用标题作为文件名，如果没有则使用job_id
    filename = f"{job.title or job_id}.pptx"
    # 清理文件名中的非法字符
    import re
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    
    return FileResponse(
        path=str(ppt_file),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )
