"""Process a single bug immediately after the QA marks it (each marker has an OBS replay buffer clip saved):
- type "record"  : trim the last PRE+POST seconds of the clip into bug{i}.mp4 (keep video)
- type "capture" : extract 1 frame as bug{i}.jpg (discard video)
Both: extract mic audio -> transcribe -> LLM writes draft issue in EN. Delete original clip when done.
"""
from pathlib import Path

import config
from pipeline import media, transcribe, issue_writer


def process_marker(session_dir: Path, bug_id: int, marker: dict) -> dict:
    """Each step (audio/transcribe/LLM/media) is best-effort: on error (e.g. missing ffmpeg,
    missing API key) set empty values but do NOT drop the bug - bugs are always written as drafts."""
    clip_path = marker["clip_path"]
    marker_type = marker.get("type", "record")

    window = config.RECORD_PRE_SECONDS + config.RECORD_POST_SECONDS

    try:
        audio_path = media.extract_audio_clip(clip_path, session_dir / f"bug{bug_id}.wav", window)
        transcripts = transcribe.transcribe_all(audio_path)
    except Exception as e:
        print(f"[bug {bug_id}] audio/transcribe error: {e}")
        transcripts = {}
    issue = issue_writer.write_issue(transcripts)

    video_clip = None
    screenshots = []
    try:
        if marker_type == "capture":
            screenshots = [media.extract_frame(clip_path, session_dir / f"bug{bug_id}.jpg")]
        else:  # record - same window as the extracted audio above
            video_clip = media.save_video_clip(clip_path, session_dir / f"bug{bug_id}.mp4", window)
    except Exception as e:
        print(f"[bug {bug_id}] media error: {e}")

    Path(clip_path).unlink(missing_ok=True)  # keep only the copy in the session dir

    return {
        "id": bug_id,
        "type": marker_type,
        "video_clip": video_clip,
        "screenshots": screenshots,
        "transcripts": transcripts,
        "issue": issue,
        "status": "draft",  # draft -> pushed (workflow states)
    }
