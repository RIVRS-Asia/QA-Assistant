"""Listens for global hotkeys to mark bugs.

- record/capture press = start a NEW bug (and save the first clip/screenshot)
- append press         = add another screenshot to the bug that is currently open

On press, calls on_marker(type) where type is "record" | "capture" | "append".
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
            config.APPEND_HOTKEY: lambda: on_marker("append"),
        })
        self._listener.start()

    def stop(self):
        if self._listener:
            self._listener.stop()
            self._listener = None
