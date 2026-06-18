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


def extract_audio_clip(clip_path: str, out_path: Path, seconds: float | None = None) -> Path:
    """Extract the MIC audio from the clip -> 16kHz mono wav (standard for ASR).

    `seconds` trims to the last N seconds (same PRE+POST window as the video clip) so the
    audio length matches the saved mp4. None = keep the whole clip.

    loudnorm normalizes the volume (EBU R128) so quiet mic recordings don't trigger
    Whisper hallucinations (e.g. spurious "đăng ký kênh" on near-silent audio).
    """
    cmd = [FFMPEG, "-y"]
    if seconds is not None:
        cmd += ["-sseof", f"-{seconds}"]
    cmd += [
        "-i", clip_path,
        "-map", f"0:a:{config.MIC_AUDIO_STREAM}",
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-ac", "1", "-ar", "16000",
        str(out_path),
    ]
    _run(cmd)
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


def extract_frame(clip_path: str, out_path: Path, seconds_from_end: float = 1) -> str:
    """Extract 1 frame at `seconds_from_end` before the clip end = the press moment.
    Capture now waits POST seconds before saving, so the press is POST seconds before the end."""
    _run([
        FFMPEG, "-y",
        "-sseof", f"-{seconds_from_end}", "-i", clip_path,
        "-frames:v", "1", "-q:v", "3",
        str(out_path),
    ])
    return out_path.name
