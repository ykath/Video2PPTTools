from __future__ import annotations

import math
from pathlib import Path
import logging

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from Src.config import VIDEO_TO_PPT_ROOT
from ..services.video_ppt_service import get_job, list_completed_jobs_for_browsing


LOGGER = logging.getLogger(__name__)
router = APIRouter()
PAGE_SIZE = 24


def _build_page_numbers(current: int, total_pages: int, window: int = 2) -> list[int]:
    if total_pages <= 0:
        return []
    start = max(1, current - window)
    end = min(total_pages, current + window)
    return list(range(start, end + 1))


@router.get("/", name="ppt_video_home", response_class=HTMLResponse)
@router.get("/ppt_video", name="ppt_video_home_alt", response_class=HTMLResponse)
def ppt_video_home(
    request: Request,
    q: str | None = Query(default=None, description="关键词检索"),
    page: int = Query(default=1, ge=1, description="页码"),
) -> HTMLResponse:
    """PPT视频浏览主页"""
    search_term = q.strip() if q else None
    current_page = max(page, 1)
    
    result = list_completed_jobs_for_browsing(page=current_page, page_size=PAGE_SIZE, search_term=search_term)
    
    total = result["total"]
    items = result["items"]
    total_pages = result["total_pages"]
    
    # 如果当前页超出范围，重定向到最后一页
    if total_pages > 0 and current_page > total_pages:
        current_page = total_pages
        result = list_completed_jobs_for_browsing(page=current_page, page_size=PAGE_SIZE, search_term=search_term)
        items = result["items"]
    
    start_index = ((current_page - 1) * PAGE_SIZE) + 1 if total else 0
    end_index = min(start_index + len(items) - 1, total) if total else 0
    
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "public/ppt_video_home.html",
        {
            "request": request,
            "videos": items,
            "total_count": total,
            "search_term": search_term or "",
            "page": current_page,
            "total_pages": total_pages,
            "page_numbers": _build_page_numbers(current_page, total_pages),
            "has_prev": current_page > 1 and total_pages > 0,
            "has_next": current_page < total_pages,
            "prev_page": current_page - 1 if current_page > 1 else None,
            "next_page": current_page + 1 if current_page < total_pages else None,
            "page_size": PAGE_SIZE,
            "result_range": (start_index, end_index),
        },
    )


@router.get("/ppt_video/play/{job_id}", name="ppt_video_player", response_class=HTMLResponse)
def ppt_video_player(job_id: str, request: Request) -> HTMLResponse:
    """PPT视频播放页"""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="视频任务不存在")

    if job.status != "completed":
        raise HTTPException(status_code=400, detail=f"视频任务未完成（当前状态：{job.status}）")

    root_path = Path(VIDEO_TO_PPT_ROOT).resolve()
    base_dir = root_path.parent.parent  # 获取部署根目录

    def _build_video_entry(path_str: str, *, is_primary: bool = False) -> dict[str, str | bool | None]:
        entry: dict[str, str | bool | None] = {
            "path": path_str,
            "label": Path(path_str).stem or Path(path_str).name,
            "filename": Path(path_str).name,
            "is_primary": is_primary,
            "url": None,
        }
        try:
            # 处理相对路径：如果路径以data/video_to_ppt_jobs开头，说明是相对路径
            if path_str.startswith("data/video_to_ppt_jobs") or path_str.startswith("data\\video_to_ppt_jobs"):
                # 转换为绝对路径
                abs_path = (base_dir / path_str).resolve()
            else:
                # 已经是绝对路径
                abs_path = Path(path_str).resolve()
            
            # 计算相对于VIDEO_TO_PPT_ROOT的路径
            relative_path = abs_path.relative_to(root_path)
            entry["url"] = request.url_for("ppt_videos", path=relative_path.as_posix())
        except ValueError:
            LOGGER.warning("Video path %s is outside of %s, cannot build stream URL", path_str, root_path)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Failed to build video entry for %s: %s", path_str, exc)
        return entry

    video_entries: list[dict[str, str | bool | None]] = []

    if job.video_files:
        for idx, path_str in enumerate(job.video_files):
            video_entries.append(_build_video_entry(path_str, is_primary=(idx == 0)))
    elif job.video_path:
        video_entries.append(_build_video_entry(job.video_path, is_primary=True))

    # 按label字符串排序
    video_entries.sort(key=lambda x: str(x.get("label", "")))
    
    # 重新设置第一个为primary
    if video_entries:
        for entry in video_entries:
            entry["is_primary"] = False
        video_entries[0]["is_primary"] = True

    video_stream_url: str | None = None
    for entry in video_entries:
        if entry.get("url"):
            video_stream_url = entry["url"]
            break

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "public/ppt_video_player.html",
        {
            "request": request,
            "job": job,
            "video_stream_url": video_stream_url,
            "video_sources": video_entries,
        },
    )


@router.get("/manage/ppt", name="manage_video_to_ppt", response_class=HTMLResponse)
def manage_video_to_ppt(request: Request) -> HTMLResponse:
    """视频转PPT管理页面"""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "manage/video_to_ppt.html",
        {"request": request},
    )

