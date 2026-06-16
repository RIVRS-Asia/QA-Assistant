"""A bug is built from one or more "parts" (each part = one hotkey press / one replay clip):
- the first press (record/capture) opens the bug
- each append press adds another screenshot part to the same bug

Per part (capture_part): trim the clip's PRE+POST window, extract mic audio -> transcribe, and
  - type "capture" : extract 1 frame as bug{id}_{part}.jpg (discard video)
  - type "record"  : keep the trimmed video as bug{id}_{part}.mp4
Then the bug is assembled once (finalize_bug): all screenshots collected into a list, all part
transcripts concatenated, and the LLM writes ONE draft issue from the combined transcript.

Every step is best-effort: on error (missing ffmpeg / API key) values are left empty but the
part/bug is never dropped - bugs are always written as drafts.
"""
from pathlib import Path

import config
from pipeline import media, transcribe, issue_writer


def capture_part(session_dir: Path, bug_id: int, part_idx: int, marker: dict) -> dict:
    """Process a single clip into a part: {screenshots, video_clip, audio, transcripts}.
    Files are named bug{id}_{part} so multiple parts of one bug never overwrite each other."""
    clip_path = marker["clip_path"]
    marker_type = marker.get("type", "capture")
    window = config.RECORD_PRE_SECONDS + config.RECORD_POST_SECONDS

    stem = f"bug{bug_id}_{part_idx}"
    audio_name = None
    transcripts = {}
    try:
        audio_path = media.extract_audio_clip(clip_path, session_dir / f"{stem}.wav", window)
        audio_name = audio_path.name
        transcripts = transcribe.transcribe_all(audio_path)
    except Exception as e:
        print(f"[bug {bug_id}.{part_idx}] audio/transcribe error: {e}")

    video_clip = None
    screenshots = []
    try:
        if marker_type == "capture":
            screenshots = [media.extract_frame(clip_path, session_dir / f"{stem}.jpg")]
        else:  # record
            video_clip = media.save_video_clip(clip_path, session_dir / f"{stem}.mp4", window)
    except Exception as e:
        print(f"[bug {bug_id}.{part_idx}] media error: {e}")

    Path(clip_path).unlink(missing_ok=True)  # keep only the copies in the session dir

    return {
        "part": part_idx,
        "type": marker_type,
        "video_clip": video_clip,
        "screenshots": screenshots,
        "audio": audio_name,
        "transcripts": transcripts,
    }


def _merge_transcripts(parts: list[dict]) -> dict:
    """Concatenate each engine's transcript across all parts (in part order) so the LLM
    sees the whole verbal description of the bug, not just one clip's window."""
    merged: dict[str, list[str]] = {}
    for p in parts:
        for engine, text in (p.get("transcripts") or {}).items():
            if text:
                merged.setdefault(engine, []).append(text)
    return {engine: "\n".join(texts) for engine, texts in merged.items()}


def finalize_bug(bug_id: int, group_type: str, parts: list[dict]) -> dict:
    """Assemble all parts of a bug into ONE draft: collect screenshots/audios, concatenate
    transcripts, and call the LLM once. parts must be ordered by part index."""
    screenshots: list[str] = []
    audios: list[str] = []
    video_clip = None
    for p in parts:
        screenshots.extend(p.get("screenshots") or [])
        if p.get("audio"):
            audios.append(p["audio"])
        if p.get("video_clip") and video_clip is None:
            video_clip = p["video_clip"]

    transcripts = _merge_transcripts(parts)
    issue = issue_writer.write_issue(transcripts)

    return {
        "id": bug_id,
        "type": group_type,
        "video_clip": video_clip,
        "screenshots": screenshots,
        "audios": audios,
        "transcripts": transcripts,
        "issue": issue,
        "status": "draft",  # draft -> pushed (workflow states)
    }
