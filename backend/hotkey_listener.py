"""Listens for global hotkeys to mark bugs.

Each press = 1 bug. On press, calls callback on_marker(type) to save the replay buffer clip.
"""
from pynput import keyboard

import config


class HotkeyListener:
    def __init__(self):
        self._listener = None

    def start(self, on_marker):
        """on_marker(marker_type: str) is called each time a hotkey is pressed (runs on pynput's thread)."""
        self._listener = keyboard.GlobalHotKeys({
            config.RECORD_HOTKEY: lambda: on_marker("record"),
            config.CAPTURE_HOTKEY: lambda: on_marker("capture"),
        })
        self._listener.start()

    def stop(self):
        if self._listener:
            self._listener.stop()
            self._listener = None
