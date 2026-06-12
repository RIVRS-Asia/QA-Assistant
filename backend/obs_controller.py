"""Điều khiển OBS qua obs-websocket v5 (thư viện obsws-python).

Yêu cầu: OBS > Tools > WebSocket Server Settings > Enable.
"""
import threading
import time

import obsws_python as obs

import config


class ObsController:
    def __init__(self):
        self._client = None
        self._lock = threading.Lock()  # client dùng chung giữa hotkey thread + status polling

    def connect(self):
        self._client = obs.ReqClient(
            host=config.OBS_HOST,
            port=config.OBS_PORT,
            password=config.OBS_PASSWORD,
            timeout=5,
        )

    def is_connected(self) -> bool:
        with self._lock:
            try:
                if self._client is None:
                    self.connect()
                self._client.get_version()
                return True
            except Exception:
                self._client = None
                return False

    # ---------- replay buffer (chỉ lưu khi nhấn hotkey, không record cả session) ----------

    def start_replay_buffer(self):
        """Bật replay buffer (OBS giữ N giây gần nhất trong RAM)."""
        if not self.is_connected():
            raise RuntimeError("Không kết nối được OBS. Kiểm tra OBS đang mở + WebSocket Server enabled.")
        with self._lock:
            if self._client.get_replay_buffer_status().output_active:
                return
            try:
                self._client.start_replay_buffer()
            except Exception:
                raise RuntimeError(
                    "OBS chưa bật Replay Buffer. Vào Settings → Output → bật "
                    "'Enable Replay Buffer', đặt Maximum Replay Time ~40s, Apply rồi thử lại."
                )
            for _ in range(50):
                if self._client.get_replay_buffer_status().output_active:
                    return
                time.sleep(0.1)
        raise RuntimeError("OBS không bật được Replay Buffer sau 5s.")

    def stop_replay_buffer(self):
        if not self.is_connected():
            return
        with self._lock:
            if self._client.get_replay_buffer_status().output_active:
                self._client.stop_replay_buffer()

    def save_replay_buffer(self) -> str:
        """Ghi đoạn buffer hiện tại ra file, trả về đường dẫn clip vừa lưu."""
        if not self.is_connected():
            raise RuntimeError("Không kết nối được OBS.")
        with self._lock:
            prev = self._last_replay_path()
            self._client.save_replay_buffer()
            for _ in range(50):  # save là async, chờ OBS ghi xong file
                path = self._last_replay_path()
                if path and path != prev:
                    return path
                time.sleep(0.1)
        raise RuntimeError("OBS không trả về clip replay sau 5s.")

    def _last_replay_path(self) -> str:
        try:
            return self._client.get_last_replay_buffer_replay().saved_replay_path
        except Exception:
            return ""

    def start_record(self) -> float:
        """Bắt đầu record, trả về epoch time lúc record start (mốc tính offset marker)."""
        if not self.is_connected():
            raise RuntimeError("Không kết nối được OBS. Kiểm tra OBS đang mở + WebSocket Server enabled.")
        status = self._client.get_record_status()
        if not status.output_active:
            self._client.start_record()
            # chờ record thực sự bắt đầu
            for _ in range(50):
                if self._client.get_record_status().output_active:
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError(
                    "OBS không bắt đầu record sau 5s. Kiểm tra OBS đã cấu hình "
                    "output path / scene hợp lệ chưa."
                )
        return time.time()

    def stop_record(self) -> str:
        """Dừng record, trả về đường dẫn file video OBS vừa lưu."""
        if not self.is_connected():
            raise RuntimeError("Không kết nối được OBS.")
        if not self._client.get_record_status().output_active:
            # recording đã không còn chạy (OBS tự dừng / chưa từng start)
            return ""
        resp = self._client.stop_record()
        return resp.output_path
