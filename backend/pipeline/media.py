"""Các thao tác ffmpeg trên clip replay buffer (clip đã là cửa sổ quanh thời điểm nhấn)."""
import subprocess
from pathlib import Path

import config


def _ffmpeg_exe() -> str:
    """Ưu tiên binary ffmpeg đi kèm gói imageio-ffmpeg (cài qua pip, không cần setup PATH);
    không có thì rơi về 'ffmpeg' trên PATH hệ thống."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


FFMPEG = _ffmpeg_exe()


def _run(cmd: list[str]):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg lỗi: {result.stderr[-500:]}")


def extract_audio_clip(clip_path: str, out_path: Path) -> Path:
    """Trích toàn bộ audio MIC của clip -> wav 16kHz mono (chuẩn cho ASR)."""
    _run([
        FFMPEG, "-y",
        "-i", clip_path,
        "-map", f"0:a:{config.MIC_AUDIO_STREAM}",
        "-ac", "1", "-ar", "16000",
        str(out_path),
    ])
    return out_path


def save_video_clip(clip_path: str, out_path: Path, seconds: float) -> str:
    """Cắt `seconds` giây cuối clip replay (= cửa sổ PRE+POST quanh lúc nhấn) -> mp4."""
    _run([
        FFMPEG, "-y",
        "-sseof", f"-{seconds}",
        "-i", clip_path,
        "-c", "copy",
        str(out_path),
    ])
    return out_path.name


def extract_frame(clip_path: str, out_path: Path) -> str:
    """Lấy 1 frame gần cuối clip (thời điểm nhấn hotkey) làm screenshot."""
    _run([
        FFMPEG, "-y",
        "-sseof", "-1", "-i", clip_path,
        "-frames:v", "1", "-q:v", "3",
        str(out_path),
    ])
    return out_path.name
