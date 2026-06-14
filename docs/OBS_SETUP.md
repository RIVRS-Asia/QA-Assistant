# OBS Configuration for QA Assistant

This document packages the "golden" OBS configuration for recording bugs with **sharp text, compact files, playable in app + Jira**.
Can be used in two ways: (A) manually via the settings table, or (B) given to an agent to read and auto-configure.

## Why This File Exists

Default OBS often produces: **blurry text** (due to output resolution downscaling), **bloated files** (due to fixed CBR recording),
and **mkv format** (browsers cannot play it). The configuration below fixes all three.

---

## Recommended Configuration

| Setting | Value | Notes |
|---|---|---|
| **Output (Scaled) Resolution** | = **Base (Canvas) Resolution** | NO downscale → eliminates blurry text. This is the most common issue. |
| **Base (Canvas) Resolution** | = native screen resolution | Varies per machine (e.g. 1920×1080, 2560×1440, 3440×1440). |
| **Downscale Filter** | `Lanczos` | Sharpest quality (only applies when scaling is forced). |
| **FPS** | `30` | Sufficient for QA; 60 spreads bitrate thin → blurrier. |
| **Recording Quality** | `High Quality` (HQ) | Records by quality (CQP) instead of CBR → sharper + file size adapts to content. |
| **Recording Format** | `mp4` | Playable in app `<video>` tag and embeddable inline in Jira. Do NOT use mkv. |
| **Encoder** | `NVENC` (if NVIDIA GPU available), otherwise `x264` | Lightweight on CPU, sharp output. |
| **Replay Buffer** | Enabled, Max Replay Time = `40`s | App does **NOT record the full session** — saves only 1 clip (last N seconds) each time QA presses the hotkey. Clip must be long enough to capture the bug moment BEFORE the press. |

**For even sharper output:** Output Mode = *Advanced* → Rate Control = `CQP`, CQ = `18` (lower number = sharper,
larger file). HQ mode in Simple mode is equivalent to CQ ~23, which is already sufficient for QA.

---

## (A) Manual Setup in OBS GUI

1. **Settings → Video**
   - Base (Canvas) Resolution = screen resolution.
   - Output (Scaled) Resolution = **set equal to Base**.
   - Downscale Filter = `Lanczos`.
   - Common FPS Values = `30`.
2. **Settings → Output**
   - Output Mode = `Simple`.
   - Recording Format = `mp4`.
   - Recording Quality = `High Quality, Medium File Size`.
   - Encoder = `Hardware (NVENC)` if NVIDIA is available.
   - ✅ Check **Enable Replay Buffer**, **Maximum Replay Time** = `40` seconds (app uses replay buffer to save clips only when hotkey is pressed).
3. **Tools → WebSocket Server Settings** (for app to control OBS)
   - Check `Enable WebSocket server`, Port `4455`.
   - Set password → copy to `OBS_PASSWORD` in the repo's `.env` file.
4. Click **Apply / OK**.

---

## (B) Instructions for AGENT Auto-Setup

When asked to "setup OBS according to this document", the agent follows this exact procedure:

1. **Find the active profile:**
   `%APPDATA%\obs-studio\basic\profiles\<ProfileName>\basic.ini`
   (Windows: `C:\Users\<user>\AppData\Roaming\obs-studio\basic\profiles\`). If multiple profiles exist,
   the active profile is listed in `%APPDATA%\obs-studio\global.ini` under `[Basic] Profile=`.

2. **REQUIRED: verify OBS is closed** (`Get-Process obs64`). If OBS is still running, do NOT edit — OBS
   overwrites `basic.ini` on exit. Ask the user to Quit OBS first.

3. **Backup** `basic.ini` → `basic.ini.bak`.

4. **Detect native screen resolution** and GPU:
   - Resolution: `[Video] BaseCX` / `BaseCY` currently present is usually already native; if uncertain, ask user or
     read from `Get-CimInstance Win32_VideoController` / `Win32_DesktopMonitor`.
   - GPU: `Get-CimInstance Win32_VideoController | Select Name`. Contains "NVIDIA" → use NVENC.

5. **Edit the following keys in `basic.ini`** (keep all other keys unchanged):

   Section `[Video]`:
   ```
   OutputCX = <equal to BaseCX>
   OutputCY = <equal to BaseCY>
   FPSType  = 0
   FPSCommon = 30
   ScaleType = lanczos
   ```

   Section `[SimpleOutput]`:
   ```
   RecFormat2 = mp4
   RecQuality = HQ
   RecEncoder = nvenc          # if no NVIDIA, use 'x264'
   ```

   Section `[Output]`:
   ```
   Mode = Simple
   ```

6. **Tell user to reopen OBS** to load the config, then record a ~25s test to verify (sharp text, smaller file than before, .mp4 extension).

### Reference Values (applied on original machine — RTX 3060, 3440×1440 monitor)

```ini
[Video]
BaseCX=3440
BaseCY=1440
OutputCX=3440      ; = Base, no downscale
OutputCY=1440
FPSType=0
FPSCommon=30
ScaleType=lanczos
ColorFormat=NV12
ColorSpace=709
ColorRange=Partial

[SimpleOutput]
RecFormat2=mp4
RecQuality=HQ
RecEncoder=nvenc
NVENCPreset2=p5
ABitrate=160
RecRB=true         ; enable Replay Buffer (app saves clip only on hotkey press)
RecRBTime=40       ; clip length kept in buffer (seconds)

[Output]
Mode=Simple
```

> ⚠️ `BaseCX/BaseCY`, `RecFilePath`, and audio devices are **machine-specific** — do NOT copy verbatim to
> another machine. Only preserve the principles: **OutputCX/CY = BaseCX/CY**, format `mp4`, quality `HQ`, filter `lanczos`.
