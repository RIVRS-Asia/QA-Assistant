"""QA Assistant backend - FastAPI.

Chạy:  cd backend && uvicorn main:app --port 8000
UI React (vite dev) gọi vào http://localhost:8000/api/...
"""
import json
import threading
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

import config
import jira_client
from hotkey_listener import HotkeyListener
from obs_controller import ObsController
from pipeline import process_session

app = FastAPI(title="QA Assistant")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # POC chạy local
    allow_methods=["*"],
    allow_headers=["*"],
)

obs = ObsController()
hotkeys = HotkeyListener()

# state của session đang record (chỉ 1 session 1 lúc - đủ cho POC)
active_session: dict | None = None


def _session_dir(session_id: str) -> Path:
    d = config.SESSIONS_DIR / session_id
    if not d.exists():
        raise HTTPException(404, f"Không có session {session_id}")
    return d


def _load_meta(session_dir: Path) -> dict:
    return json.loads((session_dir / "session.json").read_text(encoding="utf-8"))


def _save_meta(session_dir: Path, meta: dict):
    (session_dir / "session.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---------- status ----------

@app.get("/api/status")
def status():
    return {
        "obs_connected": obs.is_connected(),
        "recording": active_session is not None,
        "active_session": active_session["id"] if active_session else None,
        "marker_count": len(hotkeys.markers) if active_session else 0,
        "hotkey": config.MARKER_HOTKEY,
        "asr_engines": {
            "gemini": bool(config.GEMINI_API_KEY),
            "groq": bool(config.GROQ_API_KEY),
        },
        "jira_mode": "real" if config.JIRA_ENABLED else "mock",
    }


# ---------- session control ----------

@app.post("/api/session/start")
def start_session():
    global active_session
    if active_session:
        raise HTTPException(400, "Đang có session khác chạy")

    record_start = obs.start_record()  # raise nếu OBS chưa mở
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    (config.SESSIONS_DIR / session_id).mkdir(parents=True, exist_ok=True)

    hotkeys.start(record_start)
    active_session = {"id": session_id, "record_start": record_start}
    return {"session_id": session_id, "hotkey": config.MARKER_HOTKEY}


@app.post("/api/session/stop")
def stop_session():
    global active_session
    if not active_session:
        raise HTTPException(400, "Không có session nào đang chạy")

    video_path = obs.stop_record()
    markers = hotkeys.stop()
    session_dir = config.SESSIONS_DIR / active_session["id"]
    _save_meta(session_dir, {
        "id": active_session["id"],
        "started_at": active_session["record_start"],
        "video_path": video_path,
        "markers": markers,
        "status": "recorded",
    })
    result = {"session_id": active_session["id"], "markers": len(markers), "video": video_path}
    active_session = None
    return result


# ---------- pipeline ----------

@app.post("/api/sessions/{session_id}/process")
def process(session_id: str):
    session_dir = _session_dir(session_id)
    meta = _load_meta(session_dir)
    if meta["status"] == "processing":
        raise HTTPException(400, "Đang xử lý rồi")

    meta["status"] = "processing"
    _save_meta(session_dir, meta)

    def run():
        try:
            process_session.process(session_dir)
            meta["status"] = "done"
        except Exception as e:
            meta["status"] = "error"
            meta["error"] = str(e)
        _save_meta(session_dir, meta)

    threading.Thread(target=run, daemon=True).start()
    return {"status": "processing"}


# ---------- sessions & drafts ----------

@app.get("/api/sessions")
def list_sessions():
    sessions = []
    for d in sorted(config.SESSIONS_DIR.iterdir(), reverse=True):
        meta_file = d / "session.json"
        if meta_file.exists():
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            meta["draft_count"] = len(meta.get("markers", []))
            sessions.append(meta)
    return sessions


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str):
    session_dir = _session_dir(session_id)
    meta = _load_meta(session_dir)
    drafts_file = session_dir / "drafts.json"
    drafts = json.loads(drafts_file.read_text(encoding="utf-8")) if drafts_file.exists() else []
    return {"meta": meta, "drafts": drafts}


@app.put("/api/sessions/{session_id}/drafts/{draft_id}")
def update_draft(session_id: str, draft_id: int, issue: dict):
    """UI sửa title/description/severity trước khi push."""
    session_dir = _session_dir(session_id)
    drafts_file = session_dir / "drafts.json"
    drafts = json.loads(drafts_file.read_text(encoding="utf-8"))
    drafts[draft_id]["issue"].update(issue)
    drafts_file.write_text(json.dumps(drafts, ensure_ascii=False, indent=2), encoding="utf-8")
    return drafts[draft_id]


@app.post("/api/sessions/{session_id}/drafts/{draft_id}/push")
def push_draft(session_id: str, draft_id: int):
    session_dir = _session_dir(session_id)
    drafts_file = session_dir / "drafts.json"
    drafts = json.loads(drafts_file.read_text(encoding="utf-8"))
    draft = drafts[draft_id]

    result = jira_client.push_issue(session_dir, draft)
    draft["status"] = "pushed"
    draft["jira_key"] = result["key"]
    drafts_file.write_text(json.dumps(drafts, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


@app.get("/api/sessions/{session_id}/files/{filename}")
def get_file(session_id: str, filename: str):
    """Serve screenshot/audio cho UI."""
    path = _session_dir(session_id) / Path(filename).name  # chặn path traversal
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path)
