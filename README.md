# Roblox QA Assistant (POC)

Pipeline tự động hoá báo bug khi QA playtest game Roblox:

```
QA chơi game → nhấn hotkey khi gặp bug + mô tả bằng lời (tiếng Việt)
→ OBS record màn hình + mic
→ Pipeline: cắt audio/screenshot quanh marker → transcribe (Gemini + Groq)
→ LLM viết draft Jira issue tiếng Anh
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
- **Settings > Output > Recording**: format **mkv** (an toàn khi crash).
- Tách track mic: **Settings > Output > Output Mode: Advanced > Recording > Audio Track** — nếu chỉ ghi mic vào track 1 thì giữ `MIC_AUDIO_STREAM=0` trong `.env`. Nếu track 1 = desktop, track 2 = mic thì đặt `MIC_AUDIO_STREAM=1`.

### 2. Backend

Cần Python 3.10+ và [ffmpeg](https://ffmpeg.org/download.html) trong PATH.

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
3. Gặp bug → nhấn `Ctrl+Shift+F9` → nói mô tả bug bằng lời (vị trí, điều gì xảy ra, cách tái hiện).
4. Xong → **Kết thúc session** → vào session → **Xử lý session**.
5. Review từng draft (screenshot + transcript + issue tiếng Anh), sửa nếu cần → **Push Jira**.

## Ghi chú kỹ thuật

- Marker lưu **offset giây từ lúc OBS start record** (sync qua obs-websocket) — không lệch timestamp.
- Clip audio cắt lùi 30s trước marker (bug luôn xảy ra trước khi QA kịp nhấn phím), chỉnh bằng `CLIP_PRE_SECONDS`.
- Transcript chạy cả Gemini + Groq để so sánh giọng vùng miền — xem mục "Transcript" trong UI, engine nào kém thì bỏ key đi là tắt.
- Issue writer cross-reference 2 transcript để tự sửa lỗi ASR.

## TODO sau POC

- [ ] Ingest log Roblox Studio theo timestamp
- [ ] Attach video clip vào Jira issue
- [ ] Auto-detect bug từ transcript khi QA quên nhấn hotkey
- [ ] Dedupe với issue Jira có sẵn (JQL search)