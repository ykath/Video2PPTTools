from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .api import ppt_routes
from .api import views as view_routes
from Src.config import VIDEO_TO_PPT_ROOT

BASE_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = BASE_DIR / "frontend"


def create_app() -> FastAPI:
    app = FastAPI(title="VideoPPT Service", version="1.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    templates = Jinja2Templates(directory=str(FRONTEND_DIR / "templates"))
    app.state.templates = templates

    static_dir = FRONTEND_DIR / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # 挂载video_to_ppt_jobs目录用于访问视频和截图
    ppt_videos_dir = Path(VIDEO_TO_PPT_ROOT)
    ppt_videos_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/ppt-videos", StaticFiles(directory=str(ppt_videos_dir)), name="ppt_videos")

    app.include_router(view_routes.router)
    app.include_router(ppt_routes.router)

    return app


app = create_app()

