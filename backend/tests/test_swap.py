"""The non-destructive auto-mark swap: apply/rollback must change only which file the bug points
to, keep both files on disk, and reject bogus swaps.

Run from backend/:  ./.venv/Scripts/python.exe -m pytest tests/test_swap.py -v
"""
import json

import pytest
from fastapi.testclient import TestClient

import config
import main


@pytest.fixture
def session_with_mark(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SESSIONS_DIR", tmp_path)
    sid = "20260101_000000"
    d = tmp_path / sid
    d.mkdir()
    (d / "bug0_0.jpg").write_bytes(b"original-frame")
    (d / "bug0_0_marked.png").write_bytes(b"boxed-copy")
    draft = {
        "id": 0, "type": "capture", "video_clip": None,
        "screenshots": ["bug0_0.jpg"], "audios": [], "transcripts": {},
        "issue": {"title": "T"}, "status": "draft",
        "auto_marks": [{"src": "bug0_0.jpg", "marked": "bug0_0_marked.png", "box": [1, 2, 3, 4]}],
    }
    (d / "drafts.json").write_text(json.dumps([draft]), encoding="utf-8")
    return sid, d


def _shots(d):
    return json.loads((d / "drafts.json").read_text(encoding="utf-8"))[0]["screenshots"]


def test_apply_then_rollback_is_reversible_and_keeps_both_files(session_with_mark):
    sid, d = session_with_mark
    with TestClient(main.app) as c:
        # apply: original -> boxed copy
        r = c.put(f"/api/sessions/{sid}/drafts/0/screenshots/bug0_0.jpg/swap", json={"to": "bug0_0_marked.png"})
        assert r.status_code == 200
        assert _shots(d) == ["bug0_0_marked.png"]
        # rollback: boxed copy -> original
        r = c.put(f"/api/sessions/{sid}/drafts/0/screenshots/bug0_0_marked.png/swap", json={"to": "bug0_0.jpg"})
        assert r.status_code == 200
        assert _shots(d) == ["bug0_0.jpg"]
    # nothing was deleted/overwritten
    assert (d / "bug0_0.jpg").read_bytes() == b"original-frame"
    assert (d / "bug0_0_marked.png").read_bytes() == b"boxed-copy"


def test_rejects_swap_to_a_non_partner_file(session_with_mark):
    sid, d = session_with_mark
    with TestClient(main.app) as c:
        r = c.put(f"/api/sessions/{sid}/drafts/0/screenshots/bug0_0.jpg/swap", json={"to": "evil.png"})
    assert r.status_code == 400
    assert _shots(d) == ["bug0_0.jpg"]  # unchanged
