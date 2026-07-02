"""Result versions: a legacy flat draft upgrades to versioned shape, "reprocess" appends a new
version (re-run AI on existing media) without touching the default, and the transcript-edited flag
+ mark-default work.

Run from backend/:  ./.venv/Scripts/python.exe -m pytest tests/test_reprocess.py -v
"""
import json

import pytest
from fastapi.testclient import TestClient

import config
import main
from pipeline import process_session


@pytest.fixture
def flat_session(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SESSIONS_DIR", tmp_path)
    sid = "20260101_000000"
    d = tmp_path / sid
    d.mkdir()
    (d / "bug0_0.jpg").write_bytes(b"frame")
    draft = {  # legacy flat draft (pre-versioning)
        "id": 0, "type": "capture", "video_clip": None,
        "screenshots": ["bug0_0.jpg"], "audios": [], "transcripts": {"gemini": "old"},
        "issue": {"title": "T"}, "status": "draft", "auto_marks": [],
    }
    (d / "drafts.json").write_text(json.dumps([draft]), encoding="utf-8")
    return sid, d


def _drafts(d):
    return json.loads((d / "drafts.json").read_text(encoding="utf-8"))


def test_normalize_shims_legacy_flat_draft():
    flat = {"id": 0, "type": "capture", "screenshots": ["a.jpg"],
            "transcripts": {"gemini": "x"}, "issue": {"title": "T"}, "status": "draft",
            "auto_marks": [{"src": "a.jpg", "marked": "a_marked.png", "box": [1, 2, 3, 4]}]}
    v = main._normalize_draft(flat)
    assert v["versions"][0]["issue"]["title"] == "T"
    assert v["default_ver"] == 0
    assert v["base_screenshots"] == ["a.jpg"]
    assert main._normalize_draft(v) is v  # idempotent


def test_normalize_recovers_originals_when_box_applied():
    # screenshot currently shows the boxed copy -> base must map back to the original frame
    flat = {"id": 0, "screenshots": ["a_marked.png"], "issue": {}, "status": "draft",
            "auto_marks": [{"src": "a.jpg", "marked": "a_marked.png", "box": [1, 2, 3, 4]}]}
    v = main._normalize_draft(flat)
    assert v["base_screenshots"] == ["a.jpg"]


def test_reprocess_creates_new_version_keeps_default(flat_session, monkeypatch):
    sid, d = flat_session
    monkeypatch.setattr(main.process_session, "reprocess_bug",
                        lambda bug_id, base, t, sd, ver, **kw: process_session._new_version(ver, t, {"title": "NEW"}, [], base))
    with TestClient(main.app) as c:
        r = c.post(f"/api/sessions/{sid}/drafts/0/reprocess", json={"transcripts": {"gemini": "fixed"}})
        assert r.status_code == 200
        body = r.json()
        assert body["ver"] == 1
        assert body["transcript_edited"] is True       # differs from baseline "old"
        assert body["issue"]["title"] == "NEW"
    draft = _drafts(d)[0]
    assert len(draft["versions"]) == 2
    assert draft["default_ver"] == 0                   # default unchanged until QA marks it


def test_reprocess_same_transcript_not_flagged(flat_session, monkeypatch):
    sid, d = flat_session
    monkeypatch.setattr(main.process_session, "reprocess_bug",
                        lambda bug_id, base, t, sd, ver, **kw: process_session._new_version(ver, t, {}, [], base))
    with TestClient(main.app) as c:
        r = c.post(f"/api/sessions/{sid}/drafts/0/reprocess", json={"transcripts": {"gemini": "old"}})
        assert r.json()["transcript_edited"] is False  # same as baseline


def test_reprocess_skips_regrounding_when_transcript_unchanged(tmp_path, monkeypatch):
    """The reported bug: re-grounding on an unchanged transcript randomly moved the box. Now the
    endpoint must pass reground=False (carry over the old box) unless the QA edited the transcript."""
    monkeypatch.setattr(config, "SESSIONS_DIR", tmp_path)
    sid = "20260101_000000"
    dd = tmp_path / sid
    dd.mkdir()
    box = {"src": "bug0_0.jpg", "marked": "bug0_0_marked.png", "box": [1, 2, 3, 4]}
    draft = {"id": 0, "type": "capture", "video_clip": None, "audios": [], "base_screenshots": ["bug0_0.jpg"],
             "default_ver": 0, "versions": [process_session._new_version(0, {"gemini": "old"}, {}, [box], ["bug0_0.jpg"])]}
    (dd / "drafts.json").write_text(json.dumps([draft]), encoding="utf-8")

    seen = {}
    def fake(bug_id, base, t, sd, ver, prev_marks=None, reground=True):
        seen["reground"] = reground
        marks = [] if reground else [dict(m) for m in (prev_marks or [])]
        return process_session._new_version(ver, t, {}, marks, base)
    monkeypatch.setattr(main.process_session, "reprocess_bug", fake)

    with TestClient(main.app) as c:
        # no transcripts in body -> baseline reused -> not edited -> reground False, box carried over
        r = c.post(f"/api/sessions/{sid}/drafts/0/reprocess", json={})
        assert r.status_code == 200
        assert seen["reground"] is False
        assert r.json()["auto_marks"] == [box]         # same box as v0, no re-roll
        # editing the transcript DOES re-ground
        c.post(f"/api/sessions/{sid}/drafts/0/reprocess", json={"transcripts": {"gemini": "new desc"}})
        assert seen["reground"] is True


def test_set_default_version(flat_session, monkeypatch):
    sid, d = flat_session
    monkeypatch.setattr(main.process_session, "reprocess_bug",
                        lambda bug_id, base, t, sd, ver, **kw: process_session._new_version(ver, t, {}, [], base))
    with TestClient(main.app) as c:
        c.post(f"/api/sessions/{sid}/drafts/0/reprocess", json={"transcripts": {"gemini": "fixed"}})
        r = c.put(f"/api/sessions/{sid}/drafts/0/default", json={"ver": 1})
        assert r.status_code == 200
    assert _drafts(d)[0]["default_ver"] == 1
