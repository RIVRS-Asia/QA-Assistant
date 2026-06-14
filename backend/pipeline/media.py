"""ffmpeg operations on replay buffer clips (clip is already the window around the press time)."""
import subprocess
from pathlib import Path

import config


def _ffmpeg_exe() -> str:
    """Prefer the ffmpeg binary bundled with imageio-ffmpeg (installed via pip, no PATH setup needed);
    fall back to 'ffmpeg' on the system PATH if not found."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


FFMPEG = _ffmpeg_exe()


def _run(cmd: list[str]):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg error: {result.stderr[-500:]}")


def extract_audio_clip(clip_path: str, out_path: Path) -> Path:
    """Extract the full MIC audio from the clip -> 16kHz mono wav (standard for ASR)."""
    _run([
        FFMPEG, "-y",
        "-i", clip_path,
        "-map", f"0:a:{config.MIC_AUDIO_STREAM}",
        "-ac", "1", "-ar", "16000",
        str(out_path),
    ])
    return out_path


def save_video_clip(clip_path: str, out_path: Path, seconds: float) -> str:
    """Trim the last `seconds` seconds of the replay clip (= PRE+POST window around the press time) -> mp4."""
    _run([
        FFMPEG, "-y",
        "-sseof", f"-{seconds}",
        "-i", clip_path,
        "-c", "copy",
        str(out_path),
    ])
    return out_path.name


def extract_frame(clip_path: str, out_path: Path) -> str:
    """Extract 1 frame near the end of the clip (the hotkey press moment) as a screenshot."""
    _run([
        FFMPEG, "-y",
        "-sseof", "-1", "-i", clip_path,
        "-frames:v", "1", "-q:v", "3",
        str(out_path),
    ])
    return out_path.name
