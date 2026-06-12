# Roblox QA Assistant (POC)

Pipeline tự động hoá báo bug khi QA playtest game Roblox:

```
QA chơi game → gặp bug: mô tả bằng lời (tiếng Việt) + nhấn hotkey
   Ctrl+Shift+F9  = VIDEO clip (20s trước + 20s sau)  |  Ctrl+Shift+F10 = SCREENSHOT (1 frame)
→ OBS Replay Buffer: mỗi lần nhấn lưu 1 clip — KHÔNG record cả session
→ Mỗi bug tự xử lý ngầm ngay: audio + (clip mp4 / frame ảnh) → transcribe (Gemini + Groq)
→ LLM viết draft Jira issue tiếng Anh → hiện dần trong bảng Bugs
→ UI review/sửa → push Jira (mock mode mặc định)
```

## Cấu trúc

```
backend/            # Python 3 - FastAPI
  main.py           # API server (session control + drafts)
  obs_controller.py # điều khiển OBS qua obs-websocket
  hotkey_listener.py# hotkey toàn cục đánh dấu bug
  jira_client.py    # push Jira (mock = ghi JSON)
  pipeline/
    media.py        # ffmpeg: cắt audio, extract screenshot
    transcribe.py   # Gemini + Groq (so sánh 2 engine)
    issue_writer.py # transcript VI -> Jira issue EN
ui/                 # React (Vite) - session control + review drafts
sessions/           # data mỗi session (tự tạo, gitignored)
```

## Setup (1 lần)

### 1. OBS

- Cài [OBS Studio](https://obsproject.com/) + bật **Tools > WebSocket Server Settings > Enable** (note lại password).
- Scene: thêm **Window Capture** trỏ vào cửa sổ Roblox (⚠️ KHÔNG dùng Game Capture — anti-cheat Byfron chặn, màn hình đen). Chạy Roblox ở windowed/borderless.
- **Cấu hình video/recording + bật Replay Buffer**: xem [`docs/OBS_SETUP.md`](docs/OBS_SETUP.md). Tóm tắt: Output resolution = Base (không downscale), filter Lanczos, 30 FPS, Quality **HQ**, format **mp4**, **bật Replay Buffer (Max Replay Time ~40s)** — app chỉ lưu clip khi nhấn hotkey.
- Tách track mic: **Settings > Output > Output Mode: Advanced > Recording > Audio Track** — nếu chỉ ghi mic vào track 1 thì giữ `MIC_AUDIO_STREAM=0` trong `.env`. Nếu track 1 = desktop, track 2 = mic thì đặt `MIC_AUDIO_STREAM=1`.

### 2. Backend

Cần Python 3.10+. ffmpeg (dùng để cắt audio/video & chụp frame) đi kèm gói
`imageio-ffmpeg` trong requirements — `pip install` là có, không cần cài thêm hay set PATH.

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

### 3. Cấu hình

```bash
copy .env.example .env
```

Điền tối thiểu: `GEMINI_API_KEY` và/hoặc `GROQ_API_KEY`, `OBS_PASSWORD`.
Jira để trống = mock mode (issue ghi ra `sessions/<id>/pushed_issues.json`).

### 4. UI

```bash
cd ui
npm install
```

## Chạy

Terminal 1 (backend — cần quyền admin trên Windows để hotkey hoạt động khi game focus):

```bash
cd backend && uvicorn main:app --port 8000
```

Terminal 2 (UI):

```bash
cd ui && npm run dev
```

Mở http://localhost:5173

## Flow sử dụng (cho QA)

1. Mở OBS (đúng scene), mở UI, kiểm tra chấm xanh "OBS đã kết nối".
2. Bấm **Bắt đầu session test** → chơi game.
3. Gặp bug → nói mô tả bug bằng lời (vị trí, điều gì xảy ra, cách tái hiện) → nhấn:
   - `Ctrl+Shift+F9` nếu bug cần **video clip** (20s trước + 20s sau lúc nhấn)
   - `Ctrl+Shift+F10` nếu bug chỉ cần **screenshot** (1 frame + transcript)
   - Mỗi bug tự xử lý ngầm và hiện dần trong bảng **Bugs** (record mất ~20s+ vì đợi quay nốt 20s sau).
4. Xong → **Kết thúc session** (đợi ~20s để bug record cuối quay xong).
5. Mở bảng **Bugs** → click 1 bug → trang chi tiết (video/ảnh + transcript + issue tiếng Anh + link Jira), sửa nếu cần → **Push Jira**.

## Ghi chú kỹ thuật

- Mỗi lần nhấn hotkey app gọi OBS `SaveReplayBuffer` qua obs-websocket. **Record** đợi `RECORD_POST_SECONDS` (20s) rồi mới lưu để clip có cả footage SAU lúc nhấn, sau đó cắt lấy `PRE+POST` giây cuối (20s trước + 20s sau). **Capture** lưu ngay, trích 1 frame. ⚠️ OBS Max Replay Time phải ≥ PRE+POST (40s).
- Bug xử lý **ngay sau mỗi lần mark** trong thread riêng (không block) → transcript + issue hiện dần, không cần bấm "Xử lý session".
- Transcript chạy cả Gemini + Groq để so sánh giọng vùng miền — xem mục "Transcript" trong UI, engine nào kém thì bỏ key đi là tắt.
- Issue writer cross-reference 2 transcript để tự sửa lỗi ASR.

## TODO sau POC

- [ ] Ingest log Roblox Studio theo timestamp
- [ ] Attach video clip vào Jira issue
- [ ] Auto-detect bug từ transcript khi QA quên nhấn hotkey
- [ ] Dedupe với issue Jira có sẵn (JQL search)