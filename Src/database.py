from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import DATABASE_PATH


class SpeechDatabase:
    def __init__(self, db_path: Path | str = DATABASE_PATH):
        self.db_path = Path(db_path)
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS speeches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id INTEGER,
                title TEXT,
                speaker TEXT,
                topic TEXT,
                speech_date TEXT,
                duration TEXT,
                video_url TEXT UNIQUE,
                mp3_path TEXT,
                raw_transcript_path TEXT,
                processed_doc_path TEXT,
                summary TEXT,
                download_status TEXT DEFAULT 'pending',
                transcription_status TEXT DEFAULT 'pending',
                postprocess_status TEXT DEFAULT 'pending',
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS video_ppt_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT UNIQUE,
                url TEXT NOT NULL,
                title TEXT,
                subtitle TEXT,
                similarity_threshold REAL,
                min_interval_seconds REAL,
                skip_first_seconds REAL,
                fill_mode INTEGER,
                image_format TEXT,
                image_quality INTEGER,
                extra_download_args TEXT,
                file_pattern TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                job_dir TEXT,
                error_message TEXT,
                video_path TEXT,
                ppt_path TEXT,
                slides_json_path TEXT,
                screenshots_dir TEXT,
                command TEXT,
                stdout TEXT,
                stderr TEXT,
                video_duration_seconds REAL,
                fps REAL,
                slide_count INTEGER,
                created_at TEXT,
                updated_at TEXT,
                started_at TEXT,
                completed_at TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_video_ppt_jobs_job_id
            ON video_ppt_jobs(job_id)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_video_ppt_jobs_status_created
            ON video_ppt_jobs(status, created_at)
            """
        )
        try:
            cursor.execute("ALTER TABLE video_ppt_jobs ADD COLUMN job_dir TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE video_ppt_jobs ADD COLUMN video_files TEXT")
        except sqlite3.OperationalError:
            pass
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def _current_timestamp(self) -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    def upsert_video(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        record = self.get_video_by_url(metadata["url"])
        now = self._current_timestamp()

        if record:
            cursor = self.connection.cursor()
            cursor.execute(
                """
                UPDATE speeches
                SET video_id = ?, title = ?, speaker = ?, topic = ?, speech_date = ?, duration = ?, updated_at = ?
                WHERE video_url = ?
                """,
                (
                    metadata.get("id"),
                    metadata.get("title"),
                    metadata.get("speaker"),
                    metadata.get("topic"),
                    metadata.get("speech_date"),
                    metadata.get("duration"),
                    now,
                    metadata["url"],
                ),
            )
            self.connection.commit()
            return self.get_video_by_url(metadata["url"])

        cursor = self.connection.cursor()
        cursor.execute(
            """
            INSERT INTO speeches (
                video_id, title, speaker, topic, speech_date, duration, video_url,
                download_status, transcription_status, postprocess_status,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', 'pending', 'pending', ?, ?)
            """,
            (
                metadata.get("id"),
                metadata.get("title"),
                metadata.get("speaker"),
                metadata.get("topic"),
                metadata.get("speech_date"),
                metadata.get("duration"),
                metadata["url"],
                now,
                now,
            ),
        )
        self.connection.commit()
        return self.get_video_by_url(metadata["url"])

    def get_video_by_url(self, url: str) -> Optional[Dict[str, Any]]:
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM speeches WHERE video_url = ?", (url,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def update_video(self, url: str, **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = self._current_timestamp()
        columns = ", ".join(f"{key} = ?" for key in fields.keys())
        values = list(fields.values())
        values.append(url)
        cursor = self.connection.cursor()
        cursor.execute(f"UPDATE speeches SET {columns} WHERE video_url = ?", values)
        self.connection.commit()

    def mark_downloaded(self, url: str, mp3_path: Optional[str]) -> None:
        self.update_video(
            url,
            download_status="completed",
            mp3_path=mp3_path,
        )

    def mark_transcribed(self, url: str, raw_path: Optional[str]) -> None:
        self.update_video(
            url,
            transcription_status="completed",
            raw_transcript_path=raw_path,
        )

    def mark_post_processed(self, url: str, processed_path: Optional[str], summary: Optional[str]) -> None:
        self.update_video(
            url,
            postprocess_status="completed",
            processed_doc_path=processed_path,
            summary=summary,
        )

    # Video-to-PPT jobs
    def insert_video_ppt_job(self, job_payload: Dict[str, Any]) -> Dict[str, Any]:
        now = self._current_timestamp()
        cursor = self.connection.cursor()
        extra_args = job_payload.get("extra_download_args")
        cursor.execute(
            """
            INSERT INTO video_ppt_jobs (
                job_id, url, title, subtitle,
                similarity_threshold, min_interval_seconds, skip_first_seconds,
                fill_mode, image_format, image_quality,
                extra_download_args, file_pattern,
                status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_payload["job_id"],
                job_payload["url"],
                job_payload.get("title"),
                job_payload.get("subtitle"),
                job_payload.get("similarity_threshold"),
                job_payload.get("min_interval_seconds"),
                job_payload.get("skip_first_seconds"),
                1 if job_payload.get("fill_mode", True) else 0,
                job_payload.get("image_format"),
                job_payload.get("image_quality"),
                json.dumps(extra_args) if extra_args is not None else None,
                job_payload.get("file_pattern"),
                job_payload.get("status", "pending"),
                now,
                now,
            ),
        )
        self.connection.commit()
        return self.get_video_ppt_job_by_job_id(job_payload["job_id"])

    def get_video_ppt_job_by_job_id(self, job_id: str) -> Optional[Dict[str, Any]]:
        cursor = self.connection.cursor()
        cursor.execute(
            "SELECT * FROM video_ppt_jobs WHERE job_id = ?",
            (job_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def list_video_ppt_jobs(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        cursor = self.connection.cursor()
        query = "SELECT * FROM video_ppt_jobs ORDER BY created_at DESC"
        if limit is not None:
            query += " LIMIT ?"
            rows = cursor.execute(query, (limit,)).fetchall()
        else:
            rows = cursor.execute(query).fetchall()
        return [dict(row) for row in rows]

    def update_video_ppt_job(self, job_id: str, **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = self._current_timestamp()
        columns = ", ".join(f"{key} = ?" for key in fields.keys())
        values = list(fields.values())
        values.append(job_id)
        cursor = self.connection.cursor()
        cursor.execute(
            f"UPDATE video_ppt_jobs SET {columns} WHERE job_id = ?",
            values,
        )
        self.connection.commit()

    def mark_video_ppt_job_started(self, job_id: str) -> None:
        now = self._current_timestamp()
        self.update_video_ppt_job(job_id, status="running", started_at=now, error_message=None)

    def mark_video_ppt_job_completed(self, job_id: str, result_payload: Dict[str, Any]) -> None:
        fields = {
            "status": "completed",
            "job_dir": result_payload.get("job_dir"),
            "video_path": result_payload.get("video_path"),
            "video_files": json.dumps(result_payload.get("video_files")) if result_payload.get("video_files") else None,
            "ppt_path": result_payload.get("ppt_path"),
            "slides_json_path": result_payload.get("slides_json_path"),
            "screenshots_dir": result_payload.get("screenshots_dir"),
            "command": json.dumps(result_payload.get("command")) if result_payload.get("command") else None,
            "stdout": result_payload.get("stdout"),
            "stderr": result_payload.get("stderr"),
            "video_duration_seconds": result_payload.get("video_duration_seconds"),
            "fps": result_payload.get("fps"),
            "slide_count": result_payload.get("slide_count"),
            "completed_at": self._current_timestamp(),
            "error_message": None,
        }
        self.update_video_ppt_job(job_id, **fields)

    def mark_video_ppt_job_failed(self, job_id: str, error_message: str) -> None:
        self.update_video_ppt_job(job_id, status="failed", error_message=error_message, completed_at=self._current_timestamp())
