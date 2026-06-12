"""Pipeline xử lý sau session: với mỗi marker ->
1. Cắt audio quanh marker (ffmpeg)
2. Transcribe (Gemini + Groq song song để so sánh)
3. Extract screenshots
4. LLM viết draft issue tiếng Anh
Kết quả lưu vào sessions/<id>/drafts.json
"""
import json
from pathlib import Path

from pipeline import media, transcribe, issue_writer


def process(session_dir: Path) -> list[dict]:
    meta = json.loads((session_dir / "session.json").read_text(encoding="utf-8"))
    video_path = meta["video_path"]
    markers = meta.get("markers", [])

    drafts = []
    for i, marker in enumerate(markers):
        offset = marker["offset_seconds"]
        print(f"[pipeline] xử lý marker {i + 1}/{len(markers)} tại {offset}s")

        audio_path = media.extract_audio_clip(video_path, offset, session_dir / f"bug{i}.wav")
        screenshots = media.extract_screenshots(video_path, offset, session_dir, i)
        transcripts = transcribe.transcribe_all(audio_path)
        issue = issue_writer.write_issue(transcripts)

        drafts.append({
            "id": i,
            "marker_offset": offset,
            "screenshots": screenshots,
            "transcripts": transcripts,
            "issue": issue,
            "status": "draft",  # draft -> pushed
        })

    (session_dir / "drafts.json").write_text(
        json.dumps(drafts, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return drafts
