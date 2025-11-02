from __future__ import annotations

import json
import hashlib
import logging
from datetime import timedelta
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

from .errors import SlideExtractionError
from .models import SlideExtractionResult, SlideInfo

LOGGER = logging.getLogger(__name__)


def _format_time(seconds: float) -> str:
    seconds_int = max(int(seconds), 0)
    return str(timedelta(seconds=seconds_int))


class SlideExtractor:
    """Detect slide changes in training videos and export screenshots."""

    def __init__(
        self,
        video_path: Path,
        output_dir: Path,
        similarity_threshold: float = 0.95,
        min_interval_seconds: float = 2.0,
        skip_first_seconds: float = 0.0,
        image_format: str = "jpg",
        image_quality: int = 95,
    ) -> None:
        self.video_path = Path(video_path)
        self.output_dir = Path(output_dir)
        self.similarity_threshold = similarity_threshold
        self.min_interval_seconds = min_interval_seconds
        self.skip_first_seconds = skip_first_seconds
        self.image_format = image_format.lower().lstrip(".")
        self.image_quality = int(image_quality)

        self.cap: Optional[cv2.VideoCapture] = None
        self.fps: float = 0.0
        self.total_frames: int = 0
        self.width: int = 0
        self.height: int = 0
        self.duration_seconds: float = 0.0

        self.last_frame_hash: Optional[str] = None
        self.last_frame_features: Optional[np.ndarray] = None

    def extract(self, json_path: Path | None = None) -> SlideExtractionResult:
        if not self.video_path.exists():
            raise SlideExtractionError(f"Video file not found: {self.video_path}")

        self.output_dir.mkdir(parents=True, exist_ok=True)

        if not self._open_video():
            raise SlideExtractionError(f"Failed to open video: {self.video_path}")

        slides: List[SlideInfo] = []
        min_interval_frames = max(int(self.min_interval_seconds * self.fps), 1)
        skip_frames = int(self.skip_first_seconds * self.fps)

        frame_index = 0
        last_saved_frame = -min_interval_frames

        try:
            while True:
                success, frame = self.cap.read()
                if not success:
                    break

                timestamp_seconds = frame_index / self.fps if self.fps > 0 else 0.0

                if frame_index < skip_frames:
                    frame_index += 1
                    continue

                if frame_index - last_saved_frame < min_interval_frames:
                    frame_index += 1
                    continue

                is_new_slide, similarity = self._is_new_slide(frame)
                if not is_new_slide:
                    frame_index += 1
                    continue

                slide_index = len(slides) + 1
                filename = f"slide_{slide_index:04d}.{self.image_format}"
                slide_path = self.output_dir / filename
                self._save_frame(frame, slide_path)

                height, width = frame.shape[:2]
                slide = SlideInfo(
                    index=slide_index,
                    filename=filename,
                    path=slide_path,
                    timestamp_seconds=timestamp_seconds,
                    timestamp_text=_format_time(timestamp_seconds),
                    width=width,
                    height=height,
                    similarity=similarity,
                )
                slides.append(slide)
                last_saved_frame = frame_index
                frame_index += 1
        finally:
            self._close_video()

        result = SlideExtractionResult(
            slides=slides,
            screenshots_dir=self.output_dir,
            video_path=self.video_path,
            fps=self.fps,
            total_frames=self.total_frames,
            duration_seconds=self.duration_seconds,
            json_path=json_path,
        )

        if json_path:
            self._write_json(json_path, result)

        LOGGER.info("Extracted %s PPT slides from %s", len(slides), self.video_path)
        return result

    def _open_video(self) -> bool:
        video_path_str = str(self.video_path.resolve())
        self.cap = cv2.VideoCapture(video_path_str, cv2.CAP_FFMPEG)
        if not self.cap.isOpened():
            self.cap = cv2.VideoCapture(video_path_str)
        if not self.cap.isOpened():
            LOGGER.error("Cannot open video: %s", self.video_path)
            return False

        fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.fps = fps if fps and fps > 0 else 25.0
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.duration_seconds = self.total_frames / self.fps if self.fps > 0 else 0.0

        LOGGER.debug(
            "Video opened: fps=%s total_frames=%s size=%sx%s duration=%ss",
            self.fps,
            self.total_frames,
            self.width,
            self.height,
            self.duration_seconds,
        )

        return True

    def _close_video(self) -> None:
        if self.cap:
            self.cap.release()
            self.cap = None

    def _compute_frame_hash(self, frame: np.ndarray) -> str:
        resized = cv2.resize(frame, (64, 64))
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        return hashlib.md5(gray.tobytes()).hexdigest()

    def _compute_frame_features(self, frame: np.ndarray) -> np.ndarray:
        resized = cv2.resize(frame, (128, 128))
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        return gray.astype("float32").flatten() / 255.0

    def _compute_similarity(self, features_a: np.ndarray, features_b: np.ndarray) -> float:
        numerator = float(np.dot(features_a, features_b))
        denominator = float(np.linalg.norm(features_a) * np.linalg.norm(features_b))
        if denominator == 0.0:
            return 0.0
        return max(min(numerator / denominator, 1.0), 0.0)

    def _is_new_slide(self, frame: np.ndarray) -> Tuple[bool, Optional[float]]:
        current_hash = self._compute_frame_hash(frame)
        if self.last_frame_hash == current_hash:
            return False, 1.0

        current_features = self._compute_frame_features(frame)
        if self.last_frame_features is None:
            self.last_frame_hash = current_hash
            self.last_frame_features = current_features
            return True, None

        similarity = self._compute_similarity(self.last_frame_features, current_features)
        if similarity >= self.similarity_threshold:
            self.last_frame_hash = current_hash
            self.last_frame_features = current_features
            return False, similarity

        self.last_frame_hash = current_hash
        self.last_frame_features = current_features
        return True, similarity

    def _save_frame(self, frame: np.ndarray, path: Path) -> None:
        params: List[int] = []
        suffix = path.suffix.lower()
        if suffix in {".jpg", ".jpeg"}:
            params = [int(cv2.IMWRITE_JPEG_QUALITY), self.image_quality]
        elif suffix == ".png":
            params = [int(cv2.IMWRITE_PNG_COMPRESSION), 3]

        if not cv2.imwrite(str(path), frame, params):
            raise SlideExtractionError(f"Failed to write frame to {path}")

    def _write_json(self, json_path: Path, result: SlideExtractionResult) -> None:
        # 将绝对路径转换为相对路径（相对于部署根目录）
        from Src.config import BASE_DIR
        
        def to_relative_path(abs_path: Path) -> str:
            """将绝对路径转换为相对路径"""
            try:
                return str(abs_path.relative_to(BASE_DIR)).replace("\\", "/")
            except (ValueError, AttributeError):
                # 如果无法转换为相对路径，返回原路径
                return str(abs_path).replace("\\", "/")
        
        payload = {
            "video_path": to_relative_path(result.video_path),
            "fps": result.fps,
            "total_frames": result.total_frames,
            "duration_seconds": result.duration_seconds,
            "slides": [
                {
                    "index": slide.index,
                    "filename": slide.filename,
                    "path": to_relative_path(slide.path),
                    "timestamp_seconds": slide.timestamp_seconds,
                    "timestamp": slide.timestamp_text,
                    "width": slide.width,
                    "height": slide.height,
                    "similarity": slide.similarity,
                }
                for slide in result.slides
            ],
        }

        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
