"""Floating always-on-top QA panel (delivery launcher).

Starts the FastAPI backend in a thread, then opens a small frameless WebView2
window pointing at the React `/panel` route. Closing the window stops everything.

Run via run.bat. In dev (Path B) just open http://localhost:5173/panel in a browser
(no always-on-top, but same UI).
"""
import threading
import time
import urllib.request
import webbrowser

import uvicorn
import webview

_window = None


class Api:
    """JS bridge: window.pywebview.api.* — keeps the tiny panel window tiny by sending
    the roomy review/annotate views to the default browser instead."""

    def open_external(self, url):
        webbrowser.open(url)

    def minimize(self):
        if _window:
            _window.minimize()

    def resize(self, width, height):
        if _window:
            _window.resize(width, height)

    def close(self):
        if _window:
            _window.destroy()


def _run_server():
    config = uvicorn.Config("main:app", host="127.0.0.1", port=8000, log_config=None)
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None  # signal handlers only work on the main thread
    server.run()


def _wait_for_server(url: str, timeout: float = 25.0) -> bool:
    for _ in range(int(timeout * 10)):
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.1)
    return False


def main():
    global _window
    threading.Thread(target=_run_server, daemon=True).start()
    _wait_for_server("http://127.0.0.1:8000/api/status")
    _window = webview.create_window(
        "QA Panel",
        "http://127.0.0.1:8000/panel",
        width=340, height=520,
        frameless=True, easy_drag=False,  # drag via the header's pywebview-drag-region
        on_top=True,
        background_color="#0f1115",
        js_api=Api(),
    )
    webview.start()


if __name__ == "__main__":
    main()
