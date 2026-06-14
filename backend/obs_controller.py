"""Controls OBS via obs-websocket v5 (obsws-python library).

Requirement: OBS > Tools > WebSocket Server Settings > Enable.
"""
import threading
import time

import obsws_python as obs

import config


class ObsController:
    def __init__(self):
        self._client = None
        self._lock = threading.Lock()  # client shared between hotkey thread + status polling

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

    # ---------- replay buffer (only saved when hotkey is pressed, does not record the whole session) ----------

    def start_replay_buffer(self):
        """Start the replay buffer (OBS keeps the last N seconds in RAM)."""
        if not self.is_connected():
            raise RuntimeError("Could not connect to OBS. Check that OBS is open + WebSocket Server is enabled.")
        with self._lock:
            if self._client.get_replay_buffer_status().output_active:
                return
            try:
                self._client.start_replay_buffer()
            except Exception:
                raise RuntimeError(
                    "OBS Replay Buffer is not enabled. Go to Settings → Output → enable "
                    "'Enable Replay Buffer', set Maximum Replay Time to ~40s, Apply, then try again."
                )
            for _ in range(50):
                if self._client.get_replay_buffer_status().output_active:
                    return
                time.sleep(0.1)
        raise RuntimeError("OBS failed to start Replay Buffer after 5s.")

    def stop_replay_buffer(self):
        if not self.is_connected():
            return
        with self._lock:
            if self._client.get_replay_buffer_status().output_active:
                self._client.stop_replay_buffer()

    def save_replay_buffer(self) -> str:
        """Save the current buffer segment to a file, return the path of the saved clip."""
        if not self.is_connected():
            raise RuntimeError("Could not connect to OBS.")
        with self._lock:
            prev = self._last_replay_path()
            self._client.save_replay_buffer()
            for _ in range(50):  # save is async, wait for OBS to finish writing the file
                path = self._last_replay_path()
                if path and path != prev:
                    return path
                time.sleep(0.1)
        raise RuntimeError("OBS did not return a replay clip after 5s.")

    def _last_replay_path(self) -> str:
        try:
            return self._client.get_last_replay_buffer_replay().saved_replay_path
        except Exception:
            return ""

    def start_record(self) -> float:
        """Start recording, return the epoch time at record start (reference for marker offset)."""
        if not self.is_connected():
            raise RuntimeError("Could not connect to OBS. Check that OBS is open + WebSocket Server is enabled.")
        status = self._client.get_record_status()
        if not status.output_active:
            self._client.start_record()
            # wait for recording to actually start
            for _ in range(50):
                if self._client.get_record_status().output_active:
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError(
                    "OBS did not start recording after 5s. Check that OBS has a valid "
                    "output path / scene configured."
                )
        return time.time()

    def stop_record(self) -> str:
        """Stop recording, return the path of the video file OBS just saved."""
        if not self.is_connected():
            raise RuntimeError("Could not connect to OBS.")
        if not self._client.get_record_status().output_active:
            # recording is no longer running (OBS stopped on its own / was never started)
            return ""
        resp = self._client.stop_record()
        return resp.output_path
