# Cấu hình OBS cho QA Assistant

Tài liệu này đóng gói cấu hình OBS "vàng" để quay bug **nét chữ, file gọn, phát được trong app + Jira**.
Dùng được theo 2 cách: (A) tự làm bằng tay theo bảng, hoặc (B) đưa cho agent đọc và tự set.

## Vì sao cần file này

Mặc định OBS hay bị: video **mờ chữ** (do downscale output resolution), **file phình** (do ghi CBR
cố định), và định dạng **mkv** (trình duyệt không phát được). Cấu hình dưới đây khắc phục cả ba.

---

## Cấu hình chuẩn

| Mục | Giá trị | Ghi chú |
|---|---|---|
| **Output (Scaled) Resolution** | = **Base (Canvas) Resolution** | KHÔNG downscale → hết mờ chữ. Đây là lỗi hay gặp nhất. |
| **Base (Canvas) Resolution** | = độ phân giải gốc màn hình | Mỗi máy mỗi khác (vd 1920×1080, 2560×1440, 3440×1440). |
| **Downscale Filter** | `Lanczos` | Nét nhất (chỉ áp dụng khi buộc phải scale). |
| **FPS** | `30` | Đủ cho QA; 60 trải bitrate mỏng → mờ hơn. |
| **Recording Quality** | `High Quality` (HQ) | Ghi theo chất lượng (CQP) thay vì CBR → nét + file co theo nội dung. |
| **Recording Format** | `mp4` | Phát được trong app `<video>` và đính kèm Jira xem inline. KHÔNG dùng mkv. |
| **Encoder** | `NVENC` (nếu có GPU NVIDIA), không thì `x264` | Nhẹ CPU, nét. |
| **Replay Buffer** | Bật, Max Replay Time = `40`s | App **không record cả session** — chỉ lưu 1 clip (N giây gần nhất) mỗi lần QA nhấn hotkey. Clip phải đủ dài để chứa khoảnh khắc bug TRƯỚC lúc nhấn. |

**Muốn nét hơn nữa:** Output Mode = *Advanced* → Rate Control = `CQP`, CQ = `18` (số nhỏ = nét hơn,
file to hơn). Chế độ HQ ở Simple mode tương đương CQ ~23, đã đủ tốt cho QA.

---

## (A) Set bằng tay trong OBS GUI

1. **Settings → Video**
   - Base (Canvas) Resolution = độ phân giải màn hình.
   - Output (Scaled) Resolution = **đặt bằng Base**.
   - Downscale Filter = `Lanczos`.
   - Common FPS Values = `30`.
2. **Settings → Output**
   - Output Mode = `Simple`.
   - Recording Format = `mp4`.
   - Recording Quality = `High Quality, Medium File Size`.
   - Encoder = `Hardware (NVENC)` nếu có NVIDIA.
   - ✅ Tích **Enable Replay Buffer**, **Maximum Replay Time** = `40` giây (app dùng replay buffer để chỉ lưu clip khi nhấn hotkey).
3. **Tools → WebSocket Server Settings** (để app điều khiển OBS)
   - Tích `Enable WebSocket server`, Port `4455`.
   - Đặt password → copy vào `OBS_PASSWORD` trong `.env` của repo.
4. Bấm **Apply / OK**.

---

## (B) Hướng dẫn cho AGENT tự set

Khi được yêu cầu "setup OBS theo tài liệu này", agent làm đúng quy trình sau:

1. **Tìm profile đang dùng:**
   `%APPDATA%\obs-studio\basic\profiles\<TênProfile>\basic.ini`
   (Windows: `C:\Users\<user>\AppData\Roaming\obs-studio\basic\profiles\`). Nếu có nhiều profile,
   profile đang active là profile được liệt kê trong `%APPDATA%\obs-studio\global.ini` mục `[Basic] Profile=`.

2. **BẮT BUỘC: kiểm tra OBS đã tắt** (`Get-Process obs64`). Nếu OBS còn chạy, KHÔNG sửa — vì OBS ghi
   đè `basic.ini` khi thoát. Yêu cầu user Quit OBS trước.

3. **Backup** `basic.ini` → `basic.ini.bak`.

4. **Phát hiện độ phân giải gốc màn hình** và GPU:
   - Resolution: `[Video] BaseCX` / `BaseCY` hiện có thường đã = native; nếu nghi ngờ, hỏi user hoặc
     đọc từ `Get-CimInstance Win32_VideoController` / `Win32_DesktopMonitor`.
   - GPU: `Get-CimInstance Win32_VideoController | Select Name`. Có "NVIDIA" → dùng NVENC.

5. **Sửa các key sau trong `basic.ini`** (giữ nguyên mọi key khác):

   Mục `[Video]`:
   ```
   OutputCX = <bằng BaseCX>
   OutputCY = <bằng BaseCY>
   FPSType  = 0
   FPSCommon = 30
   ScaleType = lanczos
   ```

   Mục `[SimpleOutput]`:
   ```
   RecFormat2 = mp4
   RecQuality = HQ
   RecEncoder = nvenc          # nếu không có NVIDIA, để 'x264'
   ```

   Mục `[Output]`:
   ```
   Mode = Simple
   ```

6. **Báo user mở lại OBS** để nạp config, rồi quay thử ~25s kiểm chứng (chữ nét, file < bản cũ, đuôi .mp4).

### Giá trị tham chiếu (đã áp dụng trên máy gốc — RTX 3060, màn 3440×1440)

```ini
[Video]
BaseCX=3440
BaseCY=1440
OutputCX=3440      ; = Base, không downscale
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
RecRB=true         ; bật Replay Buffer (app chỉ lưu clip khi nhấn hotkey)
RecRBTime=40       ; độ dài clip giữ trong buffer (giây)

[Output]
Mode=Simple
```

> ⚠️ `BaseCX/BaseCY`, `RecFilePath`, thiết bị audio là **machine-specific** — đừng copy nguyên si sang
> máy khác. Chỉ giữ nguyên tắc: **OutputCX/CY = BaseCX/CY**, format `mp4`, quality `HQ`, filter `lanczos`.
