"""Các thao tác ffmpeg: cắt audio quanh marker, extract screenshot từ video."""
import subprocess
from pathlib import Path

import config


def _run(cmd: list[str]):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg lỗi: {result.stderr[-500:]}")


def extract_audio_clip(video_path: str, marker_offset: float, out_path: Path) -> Path:
    """Cắt đoạn audio MIC quanh marker -> wav 16kHz mono (chuẩn cho ASR)."""
    start = max(0.0, marker_offset - config.CLIP_PRE_SECONDS)
    duration = config.CLIP_PRE_SECONDS + config.CLIP_POST_SECONDS
    _run([
        "ffmpeg", "-y",
        "-ss", str(start), "-t", str(duration),
        "-i", video_path,
        "-map", f"0:a:{config.MIC_AUDIO_STREAM}",
        "-ac", "1", "-ar", "16000",
        str(out_path),
    ])
    return out_path


def extract_screenshots(video_path: str, marker_offset: float, out_dir: Path, marker_index: int) -> list[str]:
    """Lấy 3 frame quanh thời điểm bug (bug thường xảy ra TRƯỚC khi QA nhấn hotkey)."""
    offsets = [marker_offset - 8, marker_offset - 3, marker_offset - 0.5]
    files = []
    for i, t in enumerate(offsets):
        if t < 0:
            continue
        out = out_dir / f"bug{marker_index}_frame{i}.jpg"
        _run([
            "ffmpeg", "-y",
            "-ss", str(t), "-i", video_path,
            "-frames:v", "1", "-q:v", "3",
            str(out),
        ])
        files.append(out.name)
    return files
