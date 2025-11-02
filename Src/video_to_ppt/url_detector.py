from __future__ import annotations

import re
from enum import Enum


class VideoSource(Enum):
    """视频来源类型"""
    BILIBILI = "bilibili"
    YOUTUBE = "youtube"
    UNKNOWN = "unknown"


def detect_video_source(url: str) -> VideoSource:
    """
    检测视频URL的来源
    
    Args:
        url: 视频URL
        
    Returns:
        VideoSource枚举值
    """
    url_lower = url.lower()
    
    # B站URL特征
    bilibili_patterns = [
        r'bilibili\.com',
        r'b23\.tv',
        r'acg\.tv',
    ]
    
    # YouTube URL特征
    youtube_patterns = [
        r'youtube\.com',
        r'youtu\.be',
        r'youtube-nocookie\.com',
    ]
    
    for pattern in bilibili_patterns:
        if re.search(pattern, url_lower):
            return VideoSource.BILIBILI
    
    for pattern in youtube_patterns:
        if re.search(pattern, url_lower):
            return VideoSource.YOUTUBE
    
    return VideoSource.UNKNOWN

