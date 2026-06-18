# Delivery / Setup on another machine

Goal: get QA Assistant running on a teammate's Windows PC with the fewest manual steps.
The target machine needs only **Python** and **OBS** — no Node (the UI ships pre-built and is
served by the backend).

## Steps on the target machine

1. **Get the code** — `git clone <repo>` (or copy the folder). Make sure `ui/dist/` is included.
2. **Install OBS — version 32.1.2** (the bundled config was made with this version; use the same
   one to avoid compatibility issues). [obsproject.com](https://obsproject.com/). Open it once so
   it creates its config folder, then **close it completely**.
3. **Run `setup.bat`** (double-click). It will:
   - install Python via winget if missing, create `backend\.venv`, install dependencies
     (`imageio-ffmpeg` bundles ffmpeg — it downloads automatically during `pip install`, no manual ffmpeg install needed; requires internet, ~70 MB);
   - ask for your transcription **API key(s)** (Gemini / Groq / OpenAI — at least one) and write `.env`;
   - copy the bundled **OBS profile + scene collection + WebSocket config** into `%APPDATA%\obs-studio`
     (the OBS password is pre-matched to `.env`, so no mismatch).
4. **Open OBS once** and select:
   - **Profile → QA-Assistant**, **Scene Collection → QA-Assistant** (top menu bar).
   - With Roblox running (windowed/borderless), double-click the **Window Capture** source and
     pick the Roblox window. *Do not use Game Capture — Byfron anti-cheat blocks it (black screen).*
   - Close OBS.
5. **Run `run.bat`** — it self-elevates to admin (required for global hotkeys), starts the server,
   and opens **http://localhost:8000**.

That's it. Day-to-day, just run `run.bat`.

## What still has to be done by hand (and why)

- **Installing OBS** and **picking the Roblox window** — the window only exists when Roblox is
  running, and its handle differs per machine, so this one click can't be pre-baked.
- **Admin rights** — global hotkeys can't be captured over a focused game window without them;
  `run.bat` requests this via UAC.

## Check these if the machine differs from the source PC

The bundled OBS profile is a copy of a known-working setup. Two values are hardware/display-specific:

- **Encoder = NVENC** (NVIDIA). On a non-NVIDIA GPU, OBS will warn — change
  *Settings → Output → Recording → Encoder* to x264 (or the available hardware encoder).
- **Canvas = 1920×1080** (Base = Output, no downscale). Recording still works (Window Capture grabs
  the Roblox window regardless), but for clean framing set *Settings → Video → Base/Output Resolution*
  to the monitor's resolution if it differs.
- **Replay Buffer must be ≥ 40s** (`RECORD_PRE_SECONDS + RECORD_POST_SECONDS`). The bundled profile
  already sets 40s; only revisit if you change those values in `.env`.

## Removing it

Run **`uninstall.bat`** to undo what `setup.bat` created: it deletes `backend\.venv` (Python deps +
ffmpeg — the bulk of the space) and `.env`, removes the QA-Assistant OBS profile/scene and restores
the original WebSocket config, and asks before touching `sessions\` (recorded QA work), `node_modules`,
or Python. It never removes your source code, `ui/dist`, or OBS itself.

## Notes

- The OBS WebSocket password lives in `obs-config/obs-websocket-config.json` (fine for internal use).
  To rotate it: change it in OBS, then update `OBS_PASSWORD` in `.env` to match.
- `setup.bat` is safe to re-run; it skips an existing `.env` and refuses to copy OBS config while
  OBS is open.
- Dev mode (two servers, hot reload) is unchanged — see the main `README.md`.
