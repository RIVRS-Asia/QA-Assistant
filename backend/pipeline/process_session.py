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
import time
from pathlib import Path

import config
from pipeline import media, transcribe, issue_writer, grounding


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
            shot = marker.get("screenshot")  # instant OBS screenshot taken at press time
            if shot and (session_dir / shot).exists():
                screenshots = [shot]
            else:  # fallback: pull the press-moment frame out of the replay clip
                screenshots = [media.extract_frame(clip_path, session_dir / f"{stem}.jpg", config.RECORD_POST_SECONDS)]
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


def _first_transcript(transcripts: dict) -> str:
    """Best available raw transcript text (VN localization may have spatial cues like 'upper right corner'),
    skipping engine error markers ('[gemini error: ...]')."""
    for engine in ("gemini", "openai", "groq"):
        text = (transcripts.get(engine) or "").strip()
        if text and not text.startswith("["):
            return text
    return ""


def _auto_annotate(bug_id: int, screenshots: list[str], transcripts: dict, session_dir: Path,
                   tag: str = "") -> list[dict]:
    """For each screenshot, ask Gemini where the bug is and burn a red box onto a *copy*. Best-effort:
    returns [{src, marked, box}] suggestions for the UI to show; never touches the original frame.
    `tag` is appended to the marked filename so reprocess versions don't overwrite each other's boxes."""
    description = _first_transcript(transcripts)
    marks = []
    for shot in screenshots:
        try:
            box = grounding.locate_bug(session_dir / shot, description)
            if not box:
                continue
            marked = media.draw_box(session_dir / shot, box, session_dir / f"{Path(shot).stem}_marked{tag}.png")
            marks.append({"src": shot, "marked": marked, "box": box})
        except Exception as e:
            print(f"[bug {bug_id}] auto-annotate {shot} failed: {e}")
    return marks


def _new_version(ver: int, transcripts: dict, issue: dict, auto_marks: list[dict],
                 screenshots: list[str]) -> dict:
    """One result version: the parts that reprocess regenerates. Caller stamps created_at /
    transcript_edited. Media (audios/video/base_screenshots) lives on the bug, shared across versions."""
    return {
        "ver": ver,
        "transcripts": transcripts,
        "transcript_edited": False,
        "issue": issue,
        "auto_marks": auto_marks,       # [{src, marked, box}] AI bug-region suggestions (QA confirms via UI)
        "screenshots": list(screenshots),
        "status": "draft",              # draft -> pushed (workflow states)
        "jira_key": "",
        "jira_url": "",
        "created_at": time.time(),
    }


def reprocess_bug(bug_id: int, base_screenshots: list[str], transcripts: dict,
                  session_dir: Path, ver: int, prev_marks: list[dict] | None = None,
                  reground: bool = True) -> dict:
    """Re-run the AI on existing media (no re-record, no re-transcribe): always write a fresh issue
    from `transcripts`, returning a new version dict (ver >= 1).

    Grounding only re-runs when `reground` (the QA edited the transcript). When the transcript is
    unchanged, re-grounding is pointless - with temperature=0 it returns the same box - so we just
    carry over `prev_marks`, which also avoids the old behaviour of a re-roll randomly moving the box."""
    issue = issue_writer.write_issue(transcripts)
    if reground:
        auto_marks = _auto_annotate(bug_id, base_screenshots, transcripts, session_dir, tag=f"_v{ver}")
    else:
        auto_marks = [dict(m) for m in (prev_marks or [])]  # reuse the existing boxes/marked files
    return _new_version(ver, transcripts, issue, auto_marks, base_screenshots)


def finalize_bug(bug_id: int, group_type: str, parts: list[dict], session_dir: Path | None = None) -> dict:
    """Assemble all parts of a bug into ONE draft: collect screenshots/audios, concatenate
    transcripts, call the LLM once, and (when session_dir is given) auto-suggest a bug-region box
    per screenshot. parts must be ordered by part index."""
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
    auto_marks = _auto_annotate(bug_id, screenshots, transcripts, session_dir) if session_dir else []

    # Versioned shape: media (audios/video/base_screenshots) is shared; each reprocess appends a
    # new version. v0 is this first AI pass. See _normalize_draft in main.py for the legacy shim.
    return {
        "id": bug_id,
        "type": group_type,
        "video_clip": video_clip,
        "audios": audios,
        "base_screenshots": list(screenshots),  # original frames, source for reprocess grounding
        "default_ver": 0,
        "versions": [_new_version(0, transcripts, issue, auto_marks, screenshots)],
    }
