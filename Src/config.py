from __future__ import annotations

import os
from pathlib import Path

# 基础路径配置 - 部署根目录
BASE_DIR = Path(__file__).resolve().parent.parent

# 数据库路径
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", BASE_DIR / "data" / "speech_videos.db"))

# 视频转PPT数据目录
VIDEO_TO_PPT_ROOT = Path(os.getenv("VIDEO_TO_PPT_ROOT", BASE_DIR / "data" / "video_to_ppt_jobs"))

# BBDown配置 - 用于下载B站视频
_bbdown_env = os.getenv("BBDOWN_EXECUTABLE", "")
if _bbdown_env:
    BBDOWN_EXECUTABLE = Path(_bbdown_env) if not Path(_bbdown_env).is_absolute() else Path(_bbdown_env)
    if not BBDOWN_EXECUTABLE.is_absolute():
        BBDOWN_EXECUTABLE = BASE_DIR / BBDOWN_EXECUTABLE
else:
    BBDOWN_EXECUTABLE = BASE_DIR / "tools" / "BBDown.exe"

# yt-dlp配置 - 用于下载YouTube视频
_ytdlp_env = os.getenv("YTDLP_EXECUTABLE", "")
if _ytdlp_env:
    YTDLP_EXECUTABLE = Path(_ytdlp_env) if not Path(_ytdlp_env).is_absolute() else Path(_ytdlp_env)
    if not YTDLP_EXECUTABLE.is_absolute():
        YTDLP_EXECUTABLE = BASE_DIR / YTDLP_EXECUTABLE
else:
    YTDLP_EXECUTABLE = BASE_DIR / "tools" / "yt-dlp.exe"

# 确保必要目录存在
for path in [VIDEO_TO_PPT_ROOT, DATABASE_PATH.parent]:
    path.mkdir(parents=True, exist_ok=True)

