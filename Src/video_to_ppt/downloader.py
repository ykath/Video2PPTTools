from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Sequence

from .errors import VideoDownloadError
from .models import VideoDownloadResult

LOGGER = logging.getLogger(__name__)


class BBDownDownloader:
    """Wrapper around BBDown.exe for downloading bilibili videos."""

    VIDEO_EXTENSIONS = (".mp4", ".flv", ".mkv", ".avi", ".ts", ".webm", ".mov", ".mpg", ".vclip")

    def __init__(self, executable: Path, default_args: Sequence[str] | None = None) -> None:
        self.executable = Path(executable).resolve()
        self.default_args = list(default_args or [])

        if not self.executable.exists():
            raise FileNotFoundError(f"BBDown executable not found: {self.executable}")
        
        if not self.executable.is_file():
            raise FileNotFoundError(f"BBDown path is not a file: {self.executable}")

    def download(
        self,
        url: str,
        output_dir: Path,
        file_pattern: str | None = None,
        extra_args: Iterable[str] | None = None,
    ) -> VideoDownloadResult:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # 使用最简单的命令格式: BBDown <url> --work-dir "指定目录"
        command: List[str] = [str(self.executable), "-tv", url, "--multi-thread", "false", "--work-dir", str(output_dir)]
        
        # 添加默认参数
        command.extend(self.default_args)

        # file-pattern和extra_args可选
        if file_pattern:
            command.extend(["-F", file_pattern])
        if extra_args:
            command.extend(extra_args)

        started_at = datetime.utcnow()
        LOGGER.info("Downloading video via BBDown: %s", url)
        LOGGER.info("BBDown command: %s", " ".join(command))
        LOGGER.info("Output directory: %s", output_dir)
        
        try:
            # 使用简单的subprocess.run调用
            import platform
            kwargs = {
                "capture_output": True,
                "text": True,
                "encoding": "gbk" if platform.system() == "Windows" else "utf-8",  # Windows下BBDown使用GBK编码
                "errors": "ignore",
                "check": False,
            }
            
            # Windows下添加CREATE_NO_WINDOW标志
            if platform.system() == "Windows":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            
            completed = subprocess.run(command, **kwargs)
        except (OSError, PermissionError) as exc:
            LOGGER.error("Failed to start BBDown. Executable: %s, Command: %s, Error: %s", 
                        self.executable, command, exc)
            raise VideoDownloadError(f"Failed to start BBDown: {exc}") from exc

        completed_at = datetime.utcnow()

        stdout = completed.stdout or ""
        stderr = completed.stderr or ""

        # 记录完整的输出信息
        LOGGER.info("BBDown stdout:\n%s", stdout)
        if stderr:
            LOGGER.warning("BBDown stderr:\n%s", stderr)
        LOGGER.info("BBDown exit code: %s", completed.returncode)

        # 尝试定位视频文件
        video_paths = self._locate_video_files(output_dir)
        
        # 即使BBDown返回错误码，只要找到了有效的视频文件就继续
        if not video_paths:
            if completed.returncode != 0:
                LOGGER.error("BBDown failed (code=%s) and no video file found", completed.returncode)
                raise VideoDownloadError(
                    f"BBDown exited with code {completed.returncode}. stderr: {stderr.strip()}"
                )
            else:
                raise VideoDownloadError("Download finished but no video file was found.")
        
        # 如果找到了视频文件但BBDown返回了错误码，记录警告但继续处理
        if completed.returncode != 0:
            LOGGER.warning("BBDown returned error code %s but video file was found, continuing...", 
                          completed.returncode)

        primary_video_path = video_paths[0]
        LOGGER.info("Video downloaded, selected primary file: %s", primary_video_path)

        # 从stdout提取视频标题
        video_title = self._extract_video_title(stdout)
        if video_title:
            LOGGER.info("Extracted video title: %s", video_title)

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
            video_title=video_title,
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
        LOGGER.info(
            "Found %d video file(s). Largest: %s (size: %d bytes)",
            len(candidates),
            candidates[0].name,
            candidates[0].stat().st_size,
        )
        return candidates

    def _extract_video_title(self, stdout: str) -> str | None:
        """从BBDown的stdout中提取视频标题"""
        if not stdout:
            return None
        
        # 匹配格式: [2025-10-31 16:06:33.387] - 视频标题: 电影CT揭秘
        match = re.search(r'\[\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3}\]\s*-\s*视频标题:\s*(.+)', stdout)
        if match:
            title = match.group(1).strip()
            return title if title else None
        
        return None
