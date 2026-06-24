"""Listens for global hotkeys to mark bugs.

- record/capture press = start a NEW bug (and save the first clip/screenshot)
- append press         = add another screenshot to the bug that is currently open

On press, calls on_marker(type) where type is "record" | "capture" | "append".

Uses the `keyboard` library (not pynput) so hotkeys are suppressed — the keypress
does NOT pass through to the focused game window or any other app.
Requires the process to run as administrator (run.bat self-elevates).
"""
import keyboard

import config


class HotkeyListener:
    def __init__(self):
        self._hooks = []

    def start(self, on_marker):
        """on_marker(marker_type: str) is called each time a hotkey is pressed."""
        bindings = [
            (config.RECORD_HOTKEY,  "record"),
            (config.CAPTURE_HOTKEY, "capture"),
            (config.APPEND_HOTKEY,  "append"),
            (config.END_HOTKEY,     "end"),
        ]
        for hotkey, marker_type in bindings:
            # suppress=True: the keypress is consumed here and does NOT reach any other app.
            h = keyboard.add_hotkey(hotkey, lambda t=marker_type: on_marker(t), suppress=True)
            self._hooks.append(h)

    def stop(self):
        for h in self._hooks:
            try:
                keyboard.remove_hotkey(h)
            except Exception:
                pass
        self._hooks.clear()
