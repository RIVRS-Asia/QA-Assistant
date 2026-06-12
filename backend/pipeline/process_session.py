"""Xử lý 1 bug ngay sau khi QA mark (mỗi marker có sẵn 1 clip replay buffer OBS đã lưu):
- type "record"  : cắt PRE+POST giây cuối clip thành bug{i}.mp4 (giữ video)
- type "capture" : trích 1 frame bug{i}.jpg (bỏ video)
Cả 2: trích audio mic -> transcribe -> LLM viết draft issue EN. Xử lý xong xoá clip gốc.
"""
from pathlib import Path

import config
from pipeline import media, transcribe, issue_writer


def process_marker(session_dir: Path, bug_id: int, marker: dict) -> dict:
    """Mỗi bước (audio/transcribe/LLM/media) đều best-effort: lỗi (vd thiếu ffmpeg,
    thiếu API key) thì cho giá trị rỗng chứ KHÔNG drop bug - bug luôn được ghi draft."""
    clip_path = marker["clip_path"]
    marker_type = marker.get("type", "record")

    try:
        audio_path = media.extract_audio_clip(clip_path, session_dir / f"bug{bug_id}.wav")
        transcripts = transcribe.transcribe_all(audio_path)
    except Exception as e:
        print(f"[bug {bug_id}] audio/transcribe lỗi: {e}")
        transcripts = {}
    issue = issue_writer.write_issue(transcripts)

    video_clip = None
    screenshots = []
    try:
        if marker_type == "capture":
            screenshots = [media.extract_frame(clip_path, session_dir / f"bug{bug_id}.jpg")]
        else:  # record
            window = config.RECORD_PRE_SECONDS + config.RECORD_POST_SECONDS
            video_clip = media.save_video_clip(clip_path, session_dir / f"bug{bug_id}.mp4", window)
    except Exception as e:
        print(f"[bug {bug_id}] media lỗi: {e}")

    Path(clip_path).unlink(missing_ok=True)  # chỉ giữ bản trong session dir

    return {
        "id": bug_id,
        "type": marker_type,
        "video_clip": video_clip,
        "screenshots": screenshots,
        "transcripts": transcripts,
        "issue": issue,
        "status": "draft",  # draft -> pushed
    }
