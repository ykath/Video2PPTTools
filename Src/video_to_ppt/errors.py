class VideoToPPTError(RuntimeError):
    """Base exception for video-to-PPT pipeline."""


class VideoDownloadError(VideoToPPTError):
    """Raised when video download fails."""


class SlideExtractionError(VideoToPPTError):
    """Raised when slide extraction fails."""


class PPTBuildError(VideoToPPTError):
    """Raised when PPT creation fails."""
