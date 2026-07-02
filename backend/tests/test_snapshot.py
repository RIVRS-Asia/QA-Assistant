"""A bug with a written draft must NOT also appear as an inflight 'analyzing' row.
Reproduces the panel's phantom 3rd-row / stuck-analyzing glitch (the finalize race).

Run from backend/:  ./.venv/Scripts/python.exe -m pytest tests/test_snapshot.py -v
"""
import json
import threading

import config
import main


def _group(bug_id):
    return {"bug_id": bug_id, "type": "capture", "status": "processing",
            "parts": [], "next_part": 0, "lock": threading.Lock()}


def test_drafted_bug_is_dropped_from_inflight(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SESSIONS_DIR", tmp_path)
    sid = "20260101_000000"
    d = tmp_path / sid
    d.mkdir()
    (d / "session.json").write_text(json.dumps({"id": sid, "markers": []}), encoding="utf-8")
    # bug 0 is finalized (draft on disk); bug 1 is still capturing (no draft yet)
    (d / "drafts.json").write_text(json.dumps([
        {"id": 0, "type": "capture", "status": "draft", "screenshots": ["bug0_0.jpg"],
         "issue": {"title": "done"}},
    ]), encoding="utf-8")
    # ...but bug 0's group still lingers in processing (the leak we defend against)
    monkeypatch.setattr(main, "active_session",
                        {"id": sid, "next_id": 2, "group": _group(1), "processing": [_group(0)]})

    snap = main._build_snapshot()
    inflight_ids = {r["bug_id"] for r in snap["inflight"]}
    assert 0 not in inflight_ids          # drafted bug dropped — no duplicate / stuck "analyzing"
    assert 1 in inflight_ids              # still-capturing bug kept
