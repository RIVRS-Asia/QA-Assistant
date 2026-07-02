"""End-to-end test of the multi-image grouping + finalize + websocket, with OBS/ffmpeg/ASR mocked.

Exercises the real code path in main._on_marker / process_session (grouping, finalize into one
draft, failed markers) without needing OBS, a game, ffmpeg, or any API key.

Run from backend/:  ./.venv/Scripts/python.exe -m pytest tests/test_grouping.py -v
"""
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import config
import main
from pipeline import media, transcribe, issue_writer


@pytest.fixture
def fast_env(tmp_path, monkeypatch):
    # Each press is processed instantly (no 20s post-roll wait) and written under tmp_path.
    monkeypatch.setattr(config, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(config, "RECORD_POST_SECONDS", 0.0)
    monkeypatch.setattr(config, "RECORD_PRE_SECONDS", 0.0)
    main.active_session = None

    # Silence the beeps and the real hotkey listener.
    for fn in ("tick", "success_new", "success_append", "error"):
        monkeypatch.setattr(main.feedback, fn, lambda *a, **k: None)
    monkeypatch.setattr(main.hotkeys, "start", lambda cb: None)
    monkeypatch.setattr(main.hotkeys, "stop", lambda: None)

    # Fake OBS: hand back a unique dummy clip file per "save".
    clip_n = {"i": 0}

    def fake_save():
        clip_n["i"] += 1
        p = tmp_path / f"clip{clip_n['i']}.mkv"
        p.write_bytes(b"fake")
        return str(p)

    monkeypatch.setattr(main.obs, "is_connected", lambda: True)
    monkeypatch.setattr(main.obs, "start_replay_buffer", lambda: None)
    monkeypatch.setattr(main.obs, "stop_replay_buffer", lambda: None)
    monkeypatch.setattr(main.obs, "save_replay_buffer", fake_save)

    # Fake ffmpeg + ASR + LLM so no external tools/keys are needed.
    def fake_audio(clip_path, out_path, seconds=None):
        Path(out_path).write_bytes(b"wav")
        return Path(out_path)

    def fake_frame(clip_path, out_path, seconds_from_end=1):
        Path(out_path).write_bytes(b"jpg")
        return Path(out_path).name

    def fake_shot(out_path):
        Path(out_path).write_bytes(b"jpg")
        return Path(out_path).name
    monkeypatch.setattr(main.obs, "screenshot", fake_shot)

    def fake_video(clip_path, out_path, seconds):
        Path(out_path).write_bytes(b"mp4")
        return Path(out_path).name

    monkeypatch.setattr(media, "extract_audio_clip", fake_audio)
    monkeypatch.setattr(media, "extract_frame", fake_frame)
    monkeypatch.setattr(media, "save_video_clip", fake_video)
    monkeypatch.setattr(transcribe, "transcribe_all", lambda p: {"gemini": "mô tả bug"})
    monkeypatch.setattr(issue_writer, "write_issue",
                        lambda t: {"title": "T", "priority": "Medium", "repro_steps": [],
                                   "actual_result": "", "expected_result": "", "labels": []})
    return tmp_path


def _drafts(session_dir: Path):
    f = session_dir / "drafts.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []


def _wait_drafts(session_dir: Path, n: int, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if len(_drafts(session_dir)) >= n:
            return _drafts(session_dir)
        time.sleep(0.05)
    return _drafts(session_dir)


def test_one_capture_then_two_appends_make_one_bug_with_three_images(fast_env):
    sid = main.start_session()["session_id"]
    session_dir = fast_env / sid

    main._on_marker("capture")   # bug #0, image 1
    main._on_marker("append")    # bug #0, image 2
    main._on_marker("append")    # bug #0, image 3
    main._on_marker("capture")   # bug #1 -> finalizes bug #0

    bugs = _wait_drafts(session_dir, 1)
    bug0 = next(b for b in bugs if b["id"] == 0)
    assert len(bug0["base_screenshots"]) == 3, bug0["base_screenshots"]
    assert len(set(bug0["base_screenshots"])) == 3   # distinct filenames, no overwrite
    transcripts = bug0["versions"][0]["transcripts"]
    assert "gemini" in transcripts
    assert transcripts["gemini"].count("mô tả bug") == 3  # 3 parts concatenated

    main.stop_session()
    bugs = _wait_drafts(session_dir, 2)          # second bug finalized on stop
    assert {b["id"] for b in bugs} == {0, 1}
    assert len(next(b for b in bugs if b["id"] == 1)["base_screenshots"]) == 1


def test_append_with_no_open_bug_starts_a_new_bug(fast_env):
    sid = main.start_session()["session_id"]
    session_dir = fast_env / sid

    main._on_marker("append")    # no bug open -> opens bug #0 (data not lost)
    main.stop_session()

    bugs = _wait_drafts(session_dir, 1)
    assert len(bugs) == 1
    assert len(bugs[0]["base_screenshots"]) == 1


def test_capture_press_shows_image_instantly(fast_env, monkeypatch):
    """The panel thumb + detail page must have the screenshot right after the press,
    while the replay clip (audio) is still pending."""
    import threading

    def fake_shot(out_path):
        Path(out_path).write_bytes(b"jpg")
        return Path(out_path).name
    monkeypatch.setattr(main.obs, "screenshot", fake_shot)

    gate = threading.Event()  # holds the clip save so the part can't finish yet
    clip_save = main.obs.save_replay_buffer

    def slow_save():
        gate.wait(5)
        return clip_save()
    monkeypatch.setattr(main.obs, "save_replay_buffer", slow_save)

    main.start_session()
    main._on_marker("capture")

    thumb = None
    deadline = time.time() + 2
    while time.time() < deadline and not thumb:
        rows = main._inflight_payload()
        thumb = rows[0]["thumb"] if rows else None
        time.sleep(0.02)
    assert thumb == "bug0_0.jpg"                      # image visible before the clip landed
    assert main._partial_bug(main.active_session["group"])["screenshots"] == ["bug0_0.jpg"]

    gate.set()
    main.stop_session()


def test_failed_clip_save_is_recorded_not_dropped(fast_env, monkeypatch):
    def boom():
        raise RuntimeError("OBS save failed")
    monkeypatch.setattr(main.obs, "save_replay_buffer", boom)

    sid = main.start_session()["session_id"]
    session_dir = fast_env / sid
    main._on_marker("capture")
    main.stop_session()
    time.sleep(0.3)

    meta = json.loads((session_dir / "session.json").read_text(encoding="utf-8"))
    failed = [m for m in meta["markers"] if m.get("failed")]
    assert len(failed) == 1                      # the lost capture is visible, not silently dropped
    assert _drafts(session_dir) == []            # no draft written for a failed clip


def test_websocket_sends_snapshot_on_connect(fast_env):
    with TestClient(main.app) as client:
        with client.websocket_connect("/api/ws") as ws:
            msg = ws.receive_json()
    assert msg["type"] == "state"
    assert "status" in msg and "sessions" in msg and "bugs" in msg
