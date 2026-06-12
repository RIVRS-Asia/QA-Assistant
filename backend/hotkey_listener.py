"""Lắng nghe hotkey toàn cục để đánh dấu bug.

Mỗi lần nhấn = 1 bug. Khi nhấn, gọi callback on_marker(type) để lưu clip replay buffer.
"""
from pynput import keyboard

import config


class HotkeyListener:
    def __init__(self):
        self._listener = None

    def start(self, on_marker):
        """on_marker(marker_type: str) được gọi mỗi lần nhấn hotkey (chạy trên thread của pynput)."""
        self._listener = keyboard.GlobalHotKeys({
            config.RECORD_HOTKEY: lambda: on_marker("record"),
            config.CAPTURE_HOTKEY: lambda: on_marker("capture"),
        })
        self._listener.start()

    def stop(self):
        if self._listener:
            self._listener.stop()
            self._listener = None
