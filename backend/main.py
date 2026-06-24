"""QA Assistant backend - FastAPI.

Run:  cd backend && uvicorn main:app --port 8000
React UI (vite dev) calls http://localhost:8000/api/... and subscribes to /api/ws for live updates
(no more polling).

Bug model: each hotkey press is a "part" of a bug.
- record/capture press = open a NEW bug (finalize the previously open one)
- append press         = add another screenshot to the bug currently open
A bug is written as ONE draft (with a list of screenshots) once all its parts finish processing.
"""
import asyncio
import json
import queue
import base64
import threading
import time
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

import config
import feedback
import jira_client
from hotkey_listener import HotkeyListener
from obs_controller import ObsController
from pipeline import process_session

app = FastAPI(title="QA Assistant")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # POC running locally
    allow_methods=["*"],
    allow_headers=["*"],
)

obs = ObsController()
hotkeys = HotkeyListener()

# state of the currently recording session (only 1 session at a time - sufficient for POC)
active_session: dict | None = None
_meta_lock = threading.Lock()      # session.json written from multiple bug threads
_drafts_lock = threading.Lock()    # drafts.json written from multiple bug threads

# Hotkey presses are dispatched through this queue so the pynput callback (which runs ON the
# Windows low-level keyboard hook) returns INSTANTLY. If that callback does real work, Windows
# drops/delays later key events -> missed & doubled hotkeys. A single worker drains the queue,
# so presses are still handled strictly in order.
_marker_queue: "queue.Queue[str | None]" = queue.Queue()
_marker_worker: threading.Thread | None = None


def _enqueue_marker(marker_type: str):
    """Hotkey callback — runs on the keyboard-hook thread, so it MUST do nothing but queue."""
    _marker_queue.put(marker_type)


def _marker_loop():
    """Single consumer: processes each press off the hook thread, in press order."""
    while True:
        marker_type = _marker_queue.get()
        if marker_type is None:  # shutdown sentinel
            return
        try:
            _on_marker(marker_type)
        except Exception as e:
            print(f"[marker] handler error: {e}")


def _ensure_marker_worker():
    global _marker_worker
    if _marker_worker is None or not _marker_worker.is_alive():
        _marker_worker = threading.Thread(target=_marker_loop, daemon=True)
        _marker_worker.start()


def _session_dir(session_id: str) -> Path:
    d = config.SESSIONS_DIR / session_id
    if not d.exists():
        raise HTTPException(404, f"Session {session_id} not found")
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


# ---------- websocket: push live state to the UI instead of polling ----------

class WSManager:
    """Broadcasts a full state snapshot to all connected UIs whenever something changes.
    notify() is thread-safe so background bug threads can trigger a broadcast."""

    def __init__(self):
        self._clients: set[WebSocket] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._clients.add(ws)
        await ws.send_json(_build_snapshot())  # initial state, so the UI needs no first fetch

    def disconnect(self, ws: WebSocket):
        self._clients.discard(ws)

    async def _broadcast(self, message: dict):
        for ws in list(self._clients):
            try:
                await ws.send_json(message)
            except Exception:
                self._clients.discard(ws)

    def notify(self):
        """Build the snapshot here (sync FS reads, off the event loop) then schedule the send."""
        if self._loop is None:
            return
        try:
            message = _build_snapshot()
            asyncio.run_coroutine_threadsafe(self._broadcast(message), self._loop)
        except Exception as e:
            print(f"[ws] notify failed: {e}")


ws_manager = WSManager()


@app.on_event("startup")
async def _capture_loop():
    ws_manager.set_loop(asyncio.get_running_loop())


@app.websocket("/api/ws")
async def ws_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()  # we don't expect client messages; this keeps the socket open
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)
    except Exception:
        ws_manager.disconnect(ws)


# ---------- state payloads (shared by REST + websocket snapshot) ----------

def _status_payload() -> dict:
    return {
        "obs_connected": obs.is_connected(),
        "recording": active_session is not None,
        "active_session": active_session["id"] if active_session else None,
        "marker_count": active_session["next_id"] if active_session else 0,
        "record_hotkey": config.RECORD_HOTKEY,
        "capture_hotkey": config.CAPTURE_HOTKEY,
        "append_hotkey": config.APPEND_HOTKEY,
        "end_hotkey": config.END_HOTKEY,
        "asr_engines": {
            "gemini": bool(config.GEMINI_API_KEY),
            "groq": bool(config.GROQ_API_KEY),
            "openai": bool(config.OPENAI_API_KEY),
        },
        "jira_mode": "real" if config.JIRA_ENABLED else "mock",
    }


def _sessions_payload() -> list[dict]:
    sessions = []
    for d in sorted(config.SESSIONS_DIR.iterdir(), reverse=True):
        meta_file = d / "session.json"
        if meta_file.exists():
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            markers = meta.get("markers", [])
            ok = [m for m in markers if not m.get("failed")]
            # markers are one-per-press now (a multi-image bug = several markers), so count distinct
            # bug_ids = number of bugs. Legacy markers had no bug_id -> fall back to marker count.
            bug_ids = {m["bug_id"] for m in ok if "bug_id" in m}
            meta["draft_count"] = len(bug_ids) if bug_ids else len(ok)
            meta["failed_count"] = sum(1 for m in markers if m.get("failed"))
            sessions.append(meta)
    return sessions


def _bugs_payload() -> list[dict]:
    bugs = []
    for d in sorted(config.SESSIONS_DIR.iterdir(), reverse=True):
        drafts_file = d / "drafts.json"
        if not drafts_file.exists():
            continue
        for draft in json.loads(drafts_file.read_text(encoding="utf-8")):
            screenshots = draft.get("screenshots", [])
            bugs.append({
                "session_id": d.name,
                "id": draft["id"],
                "type": draft.get("type", "record"),
                "title": draft["issue"].get("title", ""),
                "priority": draft["issue"].get("priority", ""),
                "status": draft["status"],
                "image_count": len(screenshots),
                "thumb": screenshots[0] if screenshots else None,  # first frame for the panel thumbnail
                "jira_key": draft.get("jira_key", ""),
                "jira_url": draft.get("jira_url", ""),
            })
    return bugs


def _row_from_group(session_id: str, g: dict) -> dict:
    """A live (not-yet-finalized) bug row for the panel: shows up the instant the hotkey is
    pressed (status 'open' = capturing) and flips to 'processing' once the bug is ended (Alt+E)."""
    with g["lock"]:
        shots = [s for p in sorted(g["parts"], key=lambda p: p["part"]) for s in (p.get("screenshots") or [])]
        ready = len(g["parts"])
    return {
        "session_id": session_id,
        "bug_id": g["bug_id"],
        "type": g["type"],
        "status": g.get("status", "open"),   # "open" (capturing) | "processing" (AI)
        "thumb": shots[0] if shots else None,
        "img_count": g["next_part"],          # presses so far (B + each A)
        "ready_count": ready,                 # parts whose clip/frame has been extracted
    }


def _inflight_payload() -> list[dict]:
    """In-memory bugs not yet written as drafts: the open one + any being AI-processed."""
    sess = active_session
    if not sess:
        return []
    rows = []
    if sess.get("group"):
        rows.append(_row_from_group(sess["id"], sess["group"]))
    for g in list(sess.get("processing", [])):  # copy: finalizer thread may remove during iteration
        rows.append(_row_from_group(sess["id"], g))
    return rows


def _build_snapshot() -> dict:
    return {
        "type": "state",
        "status": _status_payload(),
        "sessions": _sessions_payload(),
        "bugs": _bugs_payload(),
        "inflight": _inflight_payload(),
    }


# ---------- status ----------

@app.get("/api/status")
def status():
    return _status_payload()


# ---------- session control ----------

def _open_group(marker_type: str) -> dict:
    """Open a new bug and make it the current group. next_id increments per BUG (append does not)."""
    bug_id = active_session["next_id"]
    active_session["next_id"] += 1
    group = {
        "bug_id": bug_id,
        "type": marker_type,
        "status": "open",       # open (capturing) -> processing (AI) -> written as a draft
        "parts": [],            # filled by part threads (guarded by lock)
        "part_threads": [],     # joined on finalize
        "lock": threading.Lock(),
        "next_part": 0,
    }
    active_session["group"] = group
    return group


def _capture_part(session_dir: Path, group: dict, bug_id: int, part_idx: int,
                  marker_type: str, is_append: bool):
    """Thread for one press: [wait POST if record] -> save clip -> process -> store as a part.
    Beeps on success / error so the tester knows the data actually landed."""
    time.sleep(config.RECORD_POST_SECONDS)  # wait so the clip includes POST seconds after the press (record + capture)
    try:
        clip_path = obs.save_replay_buffer()
    except Exception as e:
        print(f"[bug {bug_id}.{part_idx}] replay save error: {e}")
        feedback.error()
        _append_marker(session_dir, {
            "type": marker_type, "bug_id": bug_id, "part": part_idx,
            "failed": True, "epoch": time.time(),
        })
        ws_manager.notify()
        return

    _append_marker(session_dir, {
        "type": marker_type, "bug_id": bug_id, "part": part_idx,
        "clip_path": clip_path, "epoch": time.time(),
    })
    try:
        marker = {"type": marker_type, "clip_path": clip_path}
        part = process_session.capture_part(session_dir, bug_id, part_idx, marker)
        with group["lock"]:
            group["parts"].append(part)
        feedback.success_append() if is_append else feedback.success_new()
        print(f"[bug {bug_id}.{part_idx}] saved ({marker_type})")
    except Exception as e:
        print(f"[bug {bug_id}.{part_idx}] processing error: {e}")
        feedback.error()
    ws_manager.notify()


def _add_part(session_dir: Path, group: dict, marker_type: str, is_append: bool):
    feedback.tick()  # key registered (immediate); success/error beeps come after the clip is saved
    part_idx = group["next_part"]
    group["next_part"] += 1
    t = threading.Thread(
        target=_capture_part,
        args=(session_dir, group, group["bug_id"], part_idx, marker_type, is_append),
        daemon=True,
    )
    group["part_threads"].append(t)
    active_session["pending"].append(t)
    t.start()


def _finalize_group(session_dir: Path, group: dict, sess: dict):
    """End a bug: mark it 'processing' (so the panel shows the AI spinner), wait for all parts,
    run the LLM, write ONE draft, then drop it from the in-flight list (panel shows it 'ready').
    The finalizer thread is tracked in sess['pending'] so session/stop can wait for it."""
    group["status"] = "processing"
    sess.setdefault("processing", []).append(group)
    ws_manager.notify()  # flip the row to "analyzing (AI)…" immediately

    def run():
        for t in list(group["part_threads"]):
            t.join(timeout=config.RECORD_POST_SECONDS + 30)
        with group["lock"]:
            parts = sorted(group["parts"], key=lambda p: p["part"])
        try:
            if parts:
                draft = process_session.finalize_bug(group["bug_id"], group["type"], parts)
                _append_draft(session_dir, draft)
                print(f"[bug {group['bug_id']}] finalized with {len(parts)} part(s)")
            else:
                print(f"[bug {group['bug_id']}] no parts saved - nothing to finalize")
        finally:
            try:
                sess["processing"].remove(group)
            except ValueError:
                pass
            ws_manager.notify()  # row moves from in-flight -> drafts (green "ready")

    t = threading.Thread(target=run, daemon=True)
    sess["pending"].append(t)
    t.start()


def _on_marker(marker_type: str):
    """Runs on the hotkey thread.
    record/capture = open a NEW bug; append = add an image to the open bug;
    end = finish the open bug and hand it to the AI. A new-bug press also ends the previous
    open bug (safety net) so nothing is left un-processed."""
    sess = active_session
    if sess is None:
        return
    session_dir = config.SESSIONS_DIR / sess["id"]

    if marker_type == "append":
        group = sess.get("group")
        if group is None:
            # No bug open to append to -> don't lose the image: start a new bug, and buzz to alert
            # the tester that the append went somewhere unexpected.
            feedback.error()
            group = _open_group("capture")
            _add_part(session_dir, group, "capture", is_append=False)
            print(f"[marker] append with no open bug -> opened bug #{group['bug_id']}")
        else:
            _add_part(session_dir, group, "capture", is_append=True)
            print(f"[marker] +image to bug #{group['bug_id']}")
    elif marker_type == "end":
        group = sess.get("group")
        if group is None:
            feedback.error()  # nothing open to end
            print("[marker] end with no open bug")
        else:
            feedback.tick()
            _finalize_group(session_dir, group, sess)
            sess["group"] = None
            print(f"[marker] end bug #{group['bug_id']} -> AI")
    else:  # record / capture = open a new bug (closing the previous one, if any)
        if sess.get("group") is not None:
            _finalize_group(session_dir, sess["group"], sess)
            sess["group"] = None
        group = _open_group(marker_type)
        _add_part(session_dir, group, marker_type, is_append=False)
        print(f"[marker] bug #{group['bug_id']} ({marker_type})")
    ws_manager.notify()


@app.post("/api/session/start")
def start_session():
    global active_session
    if active_session:
        raise HTTPException(400, "Another session is already running")

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

    active_session = {"id": session_id, "next_id": 0, "pending": [], "group": None, "processing": []}
    while not _marker_queue.empty():  # drop any presses left over from a previous session
        try:
            _marker_queue.get_nowait()
        except queue.Empty:
            break
    _ensure_marker_worker()
    hotkeys.start(_enqueue_marker)
    ws_manager.notify()
    return {"session_id": session_id, "record_hotkey": config.RECORD_HOTKEY,
            "capture_hotkey": config.CAPTURE_HOTKEY, "append_hotkey": config.APPEND_HOTKEY}


@app.post("/api/session/stop")
def stop_session():
    global active_session
    if not active_session:
        raise HTTPException(400, "No session is currently running")

    sess = active_session
    active_session = None  # block new markers immediately
    hotkeys.stop()
    session_dir = config.SESSIONS_DIR / sess["id"]

    # finalize the still-open bug before tearing down
    if sess.get("group") is not None:
        _finalize_group(session_dir, sess["group"], sess)
        sess["group"] = None

    def finalize():
        # wait for pending parts/finalizers (record needs POST seconds) before stopping the buffer
        for t in list(sess["pending"]):
            t.join(timeout=config.RECORD_POST_SECONDS + 40)
        obs.stop_replay_buffer()
        with _meta_lock:
            meta = _load_meta(session_dir)
            meta["status"] = "done"
            _save_meta(session_dir, meta)
        ws_manager.notify()

    threading.Thread(target=finalize, daemon=True).start()
    ws_manager.notify()
    return {"session_id": sess["id"]}


# ---------- sessions & drafts ----------

@app.get("/api/sessions")
def list_sessions():
    return _sessions_payload()


@app.get("/api/bugs")
def list_bugs():
    """All bugs (processed drafts) from all sessions - one row per bug for the Bugs table."""
    return _bugs_payload()


def _find_inflight_group(session_id: str, bug_id: int):
    """The open or AI-processing group for this bug, if it isn't a written draft yet."""
    sess = active_session
    if not sess or sess["id"] != session_id:
        return None
    groups = ([sess["group"]] if sess.get("group") else []) + list(sess.get("processing", []))
    return next((g for g in groups if g["bug_id"] == bug_id), None)


def _partial_bug(group: dict) -> dict:
    """Draft-shaped view of a not-yet-finalized bug so the detail page can show the images
    captured so far (and annotate them) while the AI is still running. The `issue` is an empty
    placeholder; `processing=True` tells the UI to keep refreshing until the real draft lands."""
    with group["lock"]:
        parts = sorted(group["parts"], key=lambda p: p["part"])
    screenshots, audios, video_clip = [], [], None
    for p in parts:
        screenshots.extend(p.get("screenshots") or [])
        if p.get("audio"):
            audios.append(p["audio"])
        if p.get("video_clip") and video_clip is None:
            video_clip = p["video_clip"]
    return {
        "id": group["bug_id"], "type": group["type"],
        "video_clip": video_clip, "screenshots": screenshots, "audios": audios,
        "transcripts": process_session._merge_transcripts(parts),
        "issue": {"title": "", "repro_steps": [], "actual_result": "",
                  "expected_result": "", "priority": "Medium"},
        "status": group.get("status", "open"),
        "processing": True,
    }


@app.get("/api/sessions/{session_id}/bugs/{bug_id}")
def get_bug(session_id: str, bug_id: int):
    """Single bug for the detail page. Includes the list of mic-audio filenames; falls back to the
    old single-file name (bug{id}.wav) for drafts created before multi-image support.
    If the bug is still capturing / being AI-processed, returns a partial view from memory."""
    session_dir = _session_dir(session_id)
    drafts_file = session_dir / "drafts.json"
    drafts = json.loads(drafts_file.read_text(encoding="utf-8")) if drafts_file.exists() else []
    draft = next((d for d in drafts if d["id"] == bug_id), None)
    if draft is None:
        group = _find_inflight_group(session_id, bug_id)
        if group is not None:
            return _partial_bug(group)
        raise HTTPException(404, "Bug not found")
    audios = draft.get("audios")
    if not audios:
        legacy = f"bug{bug_id}.wav"
        audios = [legacy] if (session_dir / legacy).exists() else []
    return {**draft, "audios": [a for a in audios if (session_dir / a).exists()]}


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str):
    session_dir = _session_dir(session_id)
    meta = _load_meta(session_dir)
    drafts_file = session_dir / "drafts.json"
    drafts = json.loads(drafts_file.read_text(encoding="utf-8")) if drafts_file.exists() else []
    failed = [m for m in meta.get("markers", []) if m.get("failed")]
    return {"meta": meta, "drafts": drafts, "failed_markers": failed}


@app.put("/api/sessions/{session_id}/drafts/{draft_id}")
def update_draft(session_id: str, draft_id: int, issue: dict):
    """UI edits title/repro_steps/actual+expected_result/priority before pushing (looked up by id, not index)."""
    session_dir = _session_dir(session_id)
    with _drafts_lock:
        drafts_file = session_dir / "drafts.json"
        drafts = json.loads(drafts_file.read_text(encoding="utf-8"))
        draft = next((d for d in drafts if d["id"] == draft_id), None)
        if draft is None:
            raise HTTPException(404, "Bug not found")
        draft["issue"].update(issue)
        drafts_file.write_text(json.dumps(drafts, ensure_ascii=False, indent=2), encoding="utf-8")
    ws_manager.notify()
    return draft


@app.delete("/api/sessions/{session_id}/drafts/{draft_id}/screenshots/{filename}")
def delete_screenshot(session_id: str, draft_id: int, filename: str):
    """Remove one screenshot from a bug (safety net for a mis-attached image). Deletes the file too."""
    session_dir = _session_dir(session_id)
    name = Path(filename).name  # block path traversal
    with _drafts_lock:
        drafts_file = session_dir / "drafts.json"
        drafts = json.loads(drafts_file.read_text(encoding="utf-8"))
        draft = next((d for d in drafts if d["id"] == draft_id), None)
        if draft is None:
            raise HTTPException(404, "Bug not found")
        draft["screenshots"] = [s for s in draft.get("screenshots", []) if s != name]
        drafts_file.write_text(json.dumps(drafts, ensure_ascii=False, indent=2), encoding="utf-8")
    (session_dir / name).unlink(missing_ok=True)
    ws_manager.notify()
    return draft


@app.post("/api/sessions/{session_id}/drafts/{draft_id}/merge")
def merge_draft(session_id: str, draft_id: int, body: dict):
    """Merge bug `draft_id` INTO bug body['into_id']: move screenshots/audios over, concatenate
    transcripts, then delete the source draft. Lets the tester fix bugs that were split by mistake.
    The target's edited issue text is kept as-is (only media + transcripts are merged in)."""
    into_id = body.get("into_id")
    if into_id is None:
        raise HTTPException(400, "into_id is required")
    if into_id == draft_id:
        raise HTTPException(400, "Cannot merge a bug into itself")
    session_dir = _session_dir(session_id)
    with _drafts_lock:
        drafts_file = session_dir / "drafts.json"
        drafts = json.loads(drafts_file.read_text(encoding="utf-8"))
        src = next((d for d in drafts if d["id"] == draft_id), None)
        dst = next((d for d in drafts if d["id"] == into_id), None)
        if src is None or dst is None:
            raise HTTPException(404, "Bug not found")
        if dst["status"] == "pushed":
            raise HTTPException(400, "Target bug already pushed to Jira")

        dst.setdefault("screenshots", []).extend(src.get("screenshots", []))
        dst.setdefault("audios", []).extend(src.get("audios", []))
        if not dst.get("video_clip") and src.get("video_clip"):
            dst["video_clip"] = src["video_clip"]
        for engine, text in (src.get("transcripts") or {}).items():
            if text:
                existing = (dst.setdefault("transcripts", {}).get(engine) or "")
                dst["transcripts"][engine] = (existing + "\n" + text).strip()

        drafts = [d for d in drafts if d["id"] != draft_id]
        drafts_file.write_text(json.dumps(drafts, ensure_ascii=False, indent=2), encoding="utf-8")
    ws_manager.notify()
    return dst


@app.post("/api/sessions/{session_id}/drafts/{draft_id}/push")
def push_draft(session_id: str, draft_id: int):
    session_dir = _session_dir(session_id)
    with _drafts_lock:
        drafts_file = session_dir / "drafts.json"
        drafts = json.loads(drafts_file.read_text(encoding="utf-8"))
        draft = next((d for d in drafts if d["id"] == draft_id), None)
        if draft is None:
            raise HTTPException(404, "Bug not found")

        result = jira_client.push_issue(session_dir, draft)
        draft["status"] = "pushed"
        draft["jira_key"] = result["key"]
        draft["jira_url"] = result.get("url", "")  # mock: empty
        drafts_file.write_text(json.dumps(drafts, ensure_ascii=False, indent=2), encoding="utf-8")
    ws_manager.notify()
    return result


@app.put("/api/sessions/{session_id}/files/{filename}/annotate")
def annotate_screenshot(session_id: str, filename: str, body: dict):
    """Overwrite a screenshot with its annotated version (PNG data URL from marker.js)."""
    name = Path(filename).name  # block path traversal
    path = _session_dir(session_id) / name
    if not path.exists():
        raise HTTPException(404)
    data_url = body.get("dataUrl", "")
    if "," not in data_url:
        raise HTTPException(400, "dataUrl required")
    path.write_bytes(base64.b64decode(data_url.split(",", 1)[1]))
    ws_manager.notify()
    return {"ok": True}


@app.get("/api/sessions/{session_id}/files/{filename}")
def get_file(session_id: str, filename: str):
    """Serve screenshot/audio/clip to the UI."""
    path = _session_dir(session_id) / Path(filename).name  # block path traversal
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path)


# ===== Serve the built React UI (production / single-machine delivery) =====
# In dev the UI runs on Vite (:5173) and proxies /api here, so ui/dist may not exist
# and this block is skipped. When delivered with a build present, the backend serves
# everything from :8000 so the target machine needs no Node.
_UI_DIST = Path(__file__).resolve().parent.parent / "ui" / "dist"
if (_UI_DIST / "index.html").exists():
    @app.get("/{full_path:path}")
    def serve_ui(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404)  # unmatched API route - don't mask it with index.html
        candidate = _UI_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)  # hashed assets, favicon, etc.
        return FileResponse(_UI_DIST / "index.html")  # SPA fallback for deep links (/sessions/*)
