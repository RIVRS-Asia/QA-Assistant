"""QA Assistant backend - FastAPI.

Chạy:  cd backend && uvicorn main:app --port 8000
UI React (vite dev) gọi vào http://localhost:8000/api/...
"""
import json
import threading
import time
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
_meta_lock = threading.Lock()      # session.json ghi từ nhiều thread bug
_drafts_lock = threading.Lock()    # drafts.json ghi từ nhiều thread bug


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


def _append_marker(session_dir: Path, marker: dict):
    with _meta_lock:
        meta = _load_meta(session_dir)
        meta["markers"].append(marker)
        _save_meta(session_dir, meta)


def _append_draft(session_dir: Path, draft: dict):
    with _drafts_lock:
        f = session_dir / "drafts.json"
        drafts = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
        drafts.append(draft)
        f.write_text(json.dumps(drafts, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------- status ----------

@app.get("/api/status")
def status():
    return {
        "obs_connected": obs.is_connected(),
        "recording": active_session is not None,
        "active_session": active_session["id"] if active_session else None,
        "marker_count": active_session["next_id"] if active_session else 0,
        "record_hotkey": config.RECORD_HOTKEY,
        "capture_hotkey": config.CAPTURE_HOTKEY,
        "asr_engines": {
            "gemini": bool(config.GEMINI_API_KEY),
            "groq": bool(config.GROQ_API_KEY),
            "openai": bool(config.OPENAI_API_KEY),
        },
        "jira_mode": "real" if config.JIRA_ENABLED else "mock",
    }


# ---------- session control ----------

def _handle_bug(session_dir: Path, bug_id: int, marker_type: str):
    """Thread cho 1 bug (không block luồng chính): [đợi POST nếu record] -> lưu clip ->
    xử lý (transcribe + LLM) -> ghi draft. Record đợi POST giây để clip có footage SAU lúc nhấn."""
    if marker_type == "record":
        time.sleep(config.RECORD_POST_SECONDS)
    try:
        clip_path = obs.save_replay_buffer()
    except Exception as e:
        print(f"[bug {bug_id}] lưu replay lỗi: {e}")
        return
    marker = {"type": marker_type, "clip_path": clip_path, "epoch": time.time()}
    _append_marker(session_dir, marker)
    try:
        draft = process_session.process_marker(session_dir, bug_id, marker)
        _append_draft(session_dir, draft)
        print(f"[bug {bug_id}] xong ({marker_type})")
    except Exception as e:
        print(f"[bug {bug_id}] xử lý lỗi: {e}")


def _on_marker(marker_type: str):
    """Chạy trên thread hotkey: mỗi lần nhấn = 1 bug, xử lý ngầm trong thread riêng."""
    sess = active_session
    if sess is None:
        return
    bug_id = sess["next_id"]
    sess["next_id"] += 1
    session_dir = config.SESSIONS_DIR / sess["id"]
    t = threading.Thread(target=_handle_bug, args=(session_dir, bug_id, marker_type), daemon=True)
    sess["pending"].append(t)
    t.start()
    print(f"[marker] bug #{bug_id} ({marker_type}) - đang xử lý ngầm")


@app.post("/api/session/start")
def start_session():
    global active_session
    if active_session:
        raise HTTPException(400, "Đang có session khác chạy")

    try:
        obs.start_replay_buffer()  # raise nếu OBS chưa mở / chưa bật replay buffer
    except Exception as e:
        raise HTTPException(400, str(e))
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = config.SESSIONS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    _save_meta(session_dir, {
        "id": session_id, "started_at": time.time(),
        "markers": [], "status": "recording",
    })

    active_session = {"id": session_id, "next_id": 0, "pending": []}
    hotkeys.start(_on_marker)
    return {"session_id": session_id,
            "record_hotkey": config.RECORD_HOTKEY, "capture_hotkey": config.CAPTURE_HOTKEY}


@app.post("/api/session/stop")
def stop_session():
    global active_session
    if not active_session:
        raise HTTPException(400, "Không có session nào đang chạy")

    sess = active_session
    active_session = None  # chặn marker mới ngay lập tức
    hotkeys.stop()
    session_dir = config.SESSIONS_DIR / sess["id"]

    def finalize():
        # đợi các bug đang chờ (record cần POST giây) lưu xong clip rồi mới tắt buffer
        for t in list(sess["pending"]):
            t.join(timeout=config.RECORD_POST_SECONDS + 8)
        obs.stop_replay_buffer()
        with _meta_lock:
            meta = _load_meta(session_dir)
            meta["status"] = "done"
            _save_meta(session_dir, meta)

    threading.Thread(target=finalize, daemon=True).start()
    return {"session_id": sess["id"]}


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


@app.get("/api/bugs")
def list_bugs():
    """Tất cả bug (draft đã xử lý) của mọi session - mỗi bug 1 dòng cho bảng Bugs."""
    bugs = []
    for d in sorted(config.SESSIONS_DIR.iterdir(), reverse=True):
        drafts_file = d / "drafts.json"
        if not drafts_file.exists():
            continue
        for draft in json.loads(drafts_file.read_text(encoding="utf-8")):
            bugs.append({
                "session_id": d.name,
                "id": draft["id"],
                "type": draft.get("type", "record"),
                "title": draft["issue"].get("title", ""),
                "severity": draft["issue"].get("severity", ""),
                "status": draft["status"],
                "jira_key": draft.get("jira_key", ""),
                "jira_url": draft.get("jira_url", ""),
            })
    return bugs


@app.get("/api/sessions/{session_id}/bugs/{bug_id}")
def get_bug(session_id: str, bug_id: int):
    """1 bug cho trang chi tiết - kèm tên file audio mic nếu đã trích được."""
    session_dir = _session_dir(session_id)
    drafts_file = session_dir / "drafts.json"
    drafts = json.loads(drafts_file.read_text(encoding="utf-8")) if drafts_file.exists() else []
    draft = next((d for d in drafts if d["id"] == bug_id), None)
    if draft is None:
        raise HTTPException(404, "Không có bug")
    wav = f"bug{bug_id}.wav"
    return {**draft, "audio": wav if (session_dir / wav).exists() else None}


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str):
    session_dir = _session_dir(session_id)
    meta = _load_meta(session_dir)
    drafts_file = session_dir / "drafts.json"
    drafts = json.loads(drafts_file.read_text(encoding="utf-8")) if drafts_file.exists() else []
    return {"meta": meta, "drafts": drafts}


@app.put("/api/sessions/{session_id}/drafts/{draft_id}")
def update_draft(session_id: str, draft_id: int, issue: dict):
    """UI sửa title/description/severity trước khi push (tìm theo id, không theo index)."""
    session_dir = _session_dir(session_id)
    with _drafts_lock:
        drafts_file = session_dir / "drafts.json"
        drafts = json.loads(drafts_file.read_text(encoding="utf-8"))
        draft = next((d for d in drafts if d["id"] == draft_id), None)
        if draft is None:
            raise HTTPException(404, "Không có bug")
        draft["issue"].update(issue)
        drafts_file.write_text(json.dumps(drafts, ensure_ascii=False, indent=2), encoding="utf-8")
    return draft


@app.post("/api/sessions/{session_id}/drafts/{draft_id}/push")
def push_draft(session_id: str, draft_id: int):
    session_dir = _session_dir(session_id)
    with _drafts_lock:
        drafts_file = session_dir / "drafts.json"
        drafts = json.loads(drafts_file.read_text(encoding="utf-8"))
        draft = next((d for d in drafts if d["id"] == draft_id), None)
        if draft is None:
            raise HTTPException(404, "Không có bug")

        result = jira_client.push_issue(session_dir, draft)
        draft["status"] = "pushed"
        draft["jira_key"] = result["key"]
        draft["jira_url"] = result.get("url", "")  # mock: trống
        drafts_file.write_text(json.dumps(drafts, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


@app.get("/api/sessions/{session_id}/files/{filename}")
def get_file(session_id: str, filename: str):
    """Serve screenshot/audio/clip cho UI."""
    path = _session_dir(session_id) / Path(filename).name  # chặn path traversal
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path)
