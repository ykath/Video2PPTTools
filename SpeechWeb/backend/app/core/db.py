from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from Src.database import SpeechDatabase


@contextmanager
def get_database() -> Iterator[SpeechDatabase]:
    """生成一个数据库连接，确保使用后关闭。"""
    db = SpeechDatabase()
    try:
        yield db
    finally:
        db.close()

