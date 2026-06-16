"""Audio feedback so the QA tester (playing in fullscreen) knows a keypress registered
and the clip was ACTUALLY saved - this is what prevents silent data loss from mis-presses.

Backend runs on the same machine as the game (local POC), so a simple winsound beep is
the most reliable channel: the tester hears it without taking eyes off the game.

- tick()           : key was received (short high tick)
- success_new()    : a new bug clip was saved (two ascending notes)
- success_append() : an extra image was added to the current bug (single note)
- error()          : save failed / no open bug to append to (low buzz)
"""
import queue
import threading

try:
    import winsound  # Windows only
    _HAS_WINSOUND = True
except ImportError:
    _HAS_WINSOUND = False


# One persistent worker plays every beep. winsound.Beep is blocking, so if each call ran on its
# own thread, rapid presses would overlap and the OS would serialize/drop them -> doubled or
# missing beeps. A single ordered queue guarantees one beep at a time, in press order, and never
# blocks the caller (the hotkey/worker thread).
_beep_queue: "queue.Queue[list[tuple[int, int]]]" = queue.Queue(maxsize=32)
_worker: threading.Thread | None = None
_worker_lock = threading.Lock()


def _ensure_worker():
    global _worker
    with _worker_lock:
        if _worker is not None and _worker.is_alive():
            return

        def run():
            while True:
                notes = _beep_queue.get()
                try:
                    for freq, dur in notes:
                        winsound.Beep(freq, dur)
                except Exception:
                    pass

        _worker = threading.Thread(target=run, daemon=True)
        _worker.start()


def _play(notes: list[tuple[int, int]]):
    """notes = [(freq_hz, duration_ms), ...]. Enqueues the beep and returns immediately.
    No-op on non-Windows so the rest of the pipeline still works."""
    if not _HAS_WINSOUND:
        return
    _ensure_worker()
    try:
        _beep_queue.put_nowait(notes)
    except queue.Full:
        pass  # under a burst of presses, skip the oldest-style backlog rather than lag behind


def tick():
    _play([(1200, 60)])


def success_new():
    _play([(880, 90), (1320, 130)])


def success_append():
    _play([(1320, 120)])


def error():
    _play([(300, 250)])
