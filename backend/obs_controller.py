"""Điều khiển OBS qua obs-websocket v5 (thư viện obsws-python).

Yêu cầu: OBS > Tools > WebSocket Server Settings > Enable.
"""
import time

import obsws_python as obs

import config


class ObsController:
    def __init__(self):
        self._client = None

    def connect(self):
        self._client = obs.ReqClient(
            host=config.OBS_HOST,
            port=config.OBS_PORT,
            password=config.OBS_PASSWORD,
            timeout=5,
        )

    def is_connected(self) -> bool:
        try:
            if self._client is None:
                self.connect()
            self._client.get_version()
            return True
        except Exception:
            self._client = None
            return False

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
