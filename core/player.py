from __future__ import annotations
from PyQt6.QtCore import QObject, pyqtSignal
from core.models import Track, PlayerState


class UnifiedPlayer(QObject):
    state_changed = pyqtSignal(PlayerState)
    track_changed = pyqtSignal(object)   # Track
    position_changed = pyqtSignal(int)   # ms
    error_occurred = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._state = PlayerState()

    @property
    def state(self) -> PlayerState:
        return self._state

    # ── internal ──────────────────────────────────────────────────────────────

    def _set_status(self, status: str) -> None:
        self._state.status = status
        self.state_changed.emit(self._state)

    # ── public API ────────────────────────────────────────────────────────────

    def load(self, track: Track) -> None:
        self._state.current_track = track
        self._state.position_ms = 0
        self._state.duration_ms = track.duration_ms
        self._set_status("loading")
        self.track_changed.emit(track)

    def on_load_success(self) -> None:
        if self._state.status != "loading":
            return
        self._set_status("playing")

    def on_load_error(self, message: str) -> None:
        if self._state.status != "loading":
            return
        self._set_status("error")
        self.error_occurred.emit(message)

    def pause(self) -> None:
        if self._state.status != "playing":
            return
        self._set_status("paused")

    def resume(self) -> None:
        if self._state.status != "paused":
            return
        self._set_status("playing")

    def stop(self) -> None:
        self._state.current_track = None
        self._state.position_ms = 0
        self._set_status("idle")

    def seek(self, position_ms: int) -> None:
        if self._state.status not in ("playing", "paused"):
            return
        clamped = max(0, min(position_ms, self._state.duration_ms))
        self._state.position_ms = clamped
        self.position_changed.emit(clamped)

    def set_volume(self, volume: int) -> None:
        self._state.volume = max(0, min(volume, 100))

    def set_shuffle(self, enabled: bool) -> None:
        self._state.shuffle = enabled

    def set_repeat_mode(self, mode: str) -> None:
        if mode not in ("none", "one", "all"):
            raise ValueError(f"Invalid repeat mode: {mode!r}")
        self._state.repeat_mode = mode

    def update_position(self, position_ms: int) -> None:
        self._state.position_ms = position_ms
        self.position_changed.emit(position_ms)
