"""Lắng nghe hotkey toàn cục để đánh dấu thời điểm bug (marker).

Marker = số giây tính từ lúc OBS bắt đầu record (offset).
"""
import time

from pynput import keyboard

import config


class HotkeyListener:
    def __init__(self):
        self._listener = None
        self._record_start = None
        self.markers: list[dict] = []

    def start(self, record_start_epoch: float):
        """Bắt đầu lắng nghe. record_start_epoch = mốc thời gian OBS start record."""
        self._record_start = record_start_epoch
        self.markers = []
        self._listener = keyboard.GlobalHotKeys({
            config.MARKER_HOTKEY: self._on_marker,
        })
        self._listener.start()

    def _on_marker(self):
        offset = round(time.time() - self._record_start, 2)
        self.markers.append({"offset_seconds": offset, "epoch": time.time()})
        print(f"[marker] bug đánh dấu tại {offset}s")

    def stop(self) -> list[dict]:
        if self._listener:
            self._listener.stop()
            self._listener = None
        return self.markers
