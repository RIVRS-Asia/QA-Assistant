# Roblox QA Assistant (POC)

Automated bug reporting pipeline for QA playtesting Roblox games:

```
QA plays game → encounters bug: describes verbally (in Vietnamese) + presses hotkey
   Ctrl+Shift+F9  = VIDEO clip (20s before + 20s after)  |  Ctrl+Shift+F10 = SCREENSHOT (1 frame)
→ OBS Replay Buffer: each press saves 1 clip — does NOT record the entire session
→ Each bug is processed automatically in the background: audio + (mp4 clip / image frame)
  → transcribe (Gemini / Groq Whisper / OpenAI Whisper — any combination, run in parallel)
→ LLM writes draft Jira issue in English (Gemini → OpenAI GPT → Groq llama, first available)
  → appears progressively in the Bugs table
→ UI review/edit → push to Jira (mock mode by default)
```

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

## Setup (one-time)

### 1. OBS

- Install [OBS Studio](https://obsproject.com/) + enable **Tools > WebSocket Server Settings > Enable** (note the password).
- Scene: add **Window Capture** pointing to the Roblox window (⚠️ do NOT use Game Capture — Byfron anti-cheat blocks it, black screen). Run Roblox in windowed/borderless mode.
- **Configure video/recording + enable Replay Buffer**: see [`docs/OBS_SETUP.md`](docs/OBS_SETUP.md). Summary: Output resolution = Base (no downscale), Lanczos filter, 30 FPS, Quality **HQ**, format **mp4**, **enable Replay Buffer (Max Replay Time ~40s)** — app only saves a clip when hotkey is pressed.
- Separate mic track: **Settings > Output > Output Mode: Advanced > Recording > Audio Track** — if only mic is recorded on track 1, keep `MIC_AUDIO_STREAM=0` in `.env`. If track 1 = desktop, track 2 = mic, set `MIC_AUDIO_STREAM=1`.

### 2. Backend

Requires Python 3.10+. ffmpeg (used to trim audio/video & capture frames) is bundled with the
`imageio-ffmpeg` package in requirements — `pip install` handles it, no additional installation or PATH setup needed.

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

### 3. Configuration

```bash
copy .env.example .env
```

Minimum required: at least one of `GEMINI_API_KEY` / `GROQ_API_KEY` / `OPENAI_API_KEY`, and `OBS_PASSWORD`.
Leave Jira fields empty = mock mode (issues written to `sessions/<id>/pushed_issues.json`).

**ASR engines** (transcription): any combination is valid — set the keys for the engines you want to use.
**Issue writer** uses the first available key in order: Gemini → OpenAI → Groq.

### 4. UI

```bash
cd ui
npm install
```

## Running

Terminal 1 (backend — requires admin privileges on Windows for hotkeys to work when game is focused):

```bash
cd backend && uvicorn main:app --port 8000
```

Terminal 2 (UI):

```bash
cd ui && npm run dev
```

Open http://localhost:5173

## Usage Flow (for QA)

1. Open OBS (correct scene), open UI, verify the green dot "OBS connected".
2. Click **Start test session** → play the game.
3. Encounter a bug → verbally describe the bug (location, what happened, how to reproduce) → press:
   - `Ctrl+Shift+F9` to open a **new bug** with a **video clip** (20s before + 20s after the press)
   - `Ctrl+Shift+F10` to open a **new bug** with a **screenshot** (1 frame + transcript)
   - `Ctrl+Shift+F11` to add **another screenshot to the bug you just marked** (one bug, multiple images)
   - **Listen for the beep** so you know the press registered and the clip was saved: two rising notes = new bug saved, one note = image added, low buzz = save failed (re-capture). The next new-bug press (F9/F10) closes the current bug.
   - Each bug is processed automatically in the background and appears progressively in the **Bugs** table (record takes ~20s+ because it waits for 20s of post-event footage). The UI updates live over WebSocket — no polling.
4. Done → **End session** (wait ~20s for the last bug recording to finish).
5. Open the **Bugs** table → click a bug → detail page (video/image + transcript + English issue + Jira link), edit if needed → **Push to Jira**.

## Technical Notes

- Each hotkey press calls OBS `SaveReplayBuffer` via obs-websocket. **Record** waits `RECORD_POST_SECONDS` (20s) before saving so the clip includes footage AFTER the press, then trims to the last `PRE+POST` seconds (20s before + 20s after). **Capture** saves immediately, extracts 1 frame. ⚠️ OBS Max Replay Time must be ≥ PRE+POST (40s).
- Bugs are processed **immediately after each mark** in a separate thread (non-blocking) → transcript + issue appear progressively, no need to click "Process session".
- Transcription supports 3 ASR engines: **Gemini Flash** (multimodal, best at regional accents + game terms), **Groq Whisper large-v3** (fast, cheap), **OpenAI Whisper** (reliable baseline). Each engine runs if its API key is set; all enabled engines run in parallel. See the "Transcript" section in the UI to compare results.
- **Issue writer** uses the first available LLM key in order: Gemini → OpenAI GPT-4o → Groq llama-3.3-70b. It cross-references all available transcripts to self-correct ASR errors.

## TODO after POC

- [ ] Ingest Roblox Studio logs by timestamp
- [x] Attach video clip + all screenshots to Jira issue (`/rest/api/3/issue/{key}/attachments`)
- [ ] Auto-detect bug from transcript when QA forgets to press hotkey
- [ ] Deduplicate against existing Jira issues (JQL search)
- [x] Multiple images per bug — `APPEND_HOTKEY` (F11) attaches extra screenshots to the open bug; the bug is finalized into one draft (screenshots list + concatenated transcript). UI has a gallery with per-image delete and a "merge into previous bug" button to fix mis-grouping.
- [ ] Mark/annotate the bug location (QA used to circle the spot on the screenshot): auto via vision LLM — feed the frame + transcript to Gemini so it returns bounding-box coords and draws the circle; and/or a manual canvas overlay in `BugDetail` to circle/arrow before pushing to Jira.
