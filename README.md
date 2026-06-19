# Roblox QA Assistant (POC)

Automated bug reporting pipeline for QA playtesting Roblox games:

1. QA plays the game → hits a bug → **describes it verbally** (in Vietnamese) and **presses a hotkey**:
   - `Ctrl+Shift+F9` = VIDEO clip (20s before + 20s after)
   - `Alt+B` = SCREENSHOT (1 frame)
   - `Alt+A` = append screenshot
2. **OBS Replay Buffer**: each press saves 1 clip — it does *not* record the whole session.
3. Each bug is processed **automatically in the background**: audio + (mp4 clip / image frame) → transcribe (Gemini / Groq Whisper / OpenAI Whisper — any combination, in parallel).
4. An **LLM writes a draft Jira issue in English** (Gemini → OpenAI GPT → Groq llama, first available) → it appears progressively in the Bugs table.
5. **UI review/edit** → push to Jira (mock mode by default).

## Structure

```
backend/            # Python 3 - FastAPI
  main.py           # API server (session control + drafts)
  obs_controller.py # controls OBS via obs-websocket
  hotkey_listener.py# global hotkey to mark bugs
  jira_client.py    # push to Jira (mock = write JSON)
  pipeline/
    media.py        # ffmpeg: trim audio, extract screenshot
    transcribe.py   # Gemini + Groq Whisper + OpenAI Whisper (parallel, any combination)
    issue_writer.py # transcript VI -> Jira issue EN (Gemini → OpenAI → Groq llama)
ui/                 # React (Vite) - session control + review drafts
sessions/           # data per session (auto-created, gitignored)
```

## Setup

`setup.bat` does almost everything: installs Python and OBS (via winget if missing), creates
`backend\.venv` + installs deps, writes `.env` (prompts for API keys), and installs the bundled OBS
profile/scene/WebSocket config. Pick your path:

### A. Just use the app

Only **Windows** needed — no Node, no Python preinstalled.

1. `git clone <repo>` (include `ui/dist/`), then double-click **`setup.bat`**.
2. Open OBS once → it's already on the **QA-Assistant** profile + scene; double-click **Window Capture** and pick the Roblox window (windowed/borderless; ⚠️ not Game Capture — Byfron blocks it) → close OBS.
3. Double-click **`run.bat`** (self-elevates for hotkeys) → opens http://localhost:8000.

Day-to-day: just `run.bat`. Full walkthrough + troubleshooting: [`docs/DELIVERY.md`](docs/DELIVERY.md).

### B. Develop / contribute

Run `setup.bat` (gives you `.venv`, `.env`, OBS config), then run the two servers with hot reload —
this needs **Node** installed for the UI:

```bash
# Terminal 1 — backend (admin required on Windows for hotkeys over a focused game)
cd backend && .venv\Scripts\activate && uvicorn main:app --reload --port 8000

# Terminal 2 — UI (Vite dev server, http://localhost:5173)
cd ui && npm install && npm run dev
```

- Edit `.env` to tune things: at least one of `GEMINI_API_KEY` / `GROQ_API_KEY` / `OPENAI_API_KEY` is required; empty Jira fields = mock mode (issues written to `sessions/<id>/pushed_issues.json`). ASR runs any combination of engines whose keys are set; the issue writer uses the first available in order Gemini → OpenAI → Groq.
- Shipping UI changes to path A? Rebuild the bundle the backend serves: `cd ui && npm run build` (regenerates `ui/dist/`), then commit it.

## Usage Flow (for QA)

1. Open OBS (correct scene), open UI, verify the green dot "OBS connected".
2. Click **Start test session** → play the game.
3. Encounter a bug → verbally describe the bug (location, what happened, how to reproduce) → press:
   - `Ctrl+Shift+F9` to open a **new bug** with a **video clip** (20s before + 20s after the press)
   - `Alt+B` (**B**ug) to open a **new bug** with a **screenshot** (1 frame + transcript)
   - `Alt+A` (**A**ppend) to add **another screenshot to the bug you just marked** (one bug, multiple images)
   - **Listen for the beep** so you know the press registered and the clip was saved: two rising notes = new bug saved, one note = image added, low buzz = save failed (re-capture). The next new-bug press (F9/Alt+B) closes the current bug.
   - Each bug is processed automatically in the background and appears progressively in the **Bugs** table (record takes ~20s+ because it waits for 20s of post-event footage). The UI updates live over WebSocket — no polling.
4. Done → **End session** (wait ~20s for the last bug recording to finish).
5. Open the **Bugs** table → click a bug → detail page (video/image + transcript + English issue + Jira link), edit if needed → **Push to Jira**.

## Technical Notes

- Each hotkey press calls OBS `SaveReplayBuffer` via obs-websocket. **Record** waits `RECORD_POST_SECONDS` (20s) before saving so the clip includes footage AFTER the press, then trims to the last `PRE+POST` seconds (20s before + 20s after). **Capture** also waits `RECORD_POST_SECONDS` before saving (so audio = 20s before + 20s after the press), then extracts the frame at the press moment (`POST` seconds before clip end). ⚠️ OBS Max Replay Time must be ≥ PRE+POST (40s).
- Bugs are processed **immediately after each mark** in a separate thread (non-blocking) → transcript + issue appear progressively, no need to click "Process session".
- Transcription supports 3 ASR engines: **Gemini Flash** (multimodal, best at regional accents + game terms), **Groq Whisper large-v3** (fast, cheap), **OpenAI Whisper** (reliable baseline). Each engine runs if its API key is set; all enabled engines run in parallel. See the "Transcript" section in the UI to compare results.
- **Issue writer** uses the first available LLM key in order: Gemini → OpenAI GPT-4o → Groq llama-3.3-70b. It cross-references all available transcripts to self-correct ASR errors.