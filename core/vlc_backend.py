from __future__ import annotations
import logging
from PyQt6.QtCore import QObject, pyqtSignal, QMetaObject, Qt, Q_ARG

logger = logging.getLogger(__name__)

try:
    import vlc
except Exception as _vlc_err:
    vlc = None  # type: ignore[assignment]
    logger.warning("python-vlc could not load libvlc: %s — audio playback disabled. Install VLC: https://www.videolan.org", _vlc_err)


class VLCBackend(QObject):
    """python-vlc wrapper that marshals VLC events back to the Qt main thread."""

    position_changed = pyqtSignal(int)   # ms
    end_reached = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        if vlc is None:
            self._instance = None
            self._player = None
            return
        self._instance = vlc.Instance("--no-xlib")
        self._player = self._instance.media_player_new()
        self._wire_events()

    def _wire_events(self) -> None:
        if self._player is None:
            return
        em = self._player.event_manager()
        em.event_attach(
            vlc.EventType.MediaPlayerTimeChanged,
            self._on_time_changed,
        )
        em.event_attach(
            vlc.EventType.MediaPlayerEndReached,
            self._on_end_reached,
        )
        em.event_attach(
            vlc.EventType.MediaPlayerEncounteredError,
            self._on_error,
        )

    # ── VLC event callbacks (background thread) ───────────────────────────────

    def _on_time_changed(self, event) -> None:
        ms = self._player.get_time()
        QMetaObject.invokeMethod(
            self,
            "_emit_position",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(int, ms),
        )

    def _on_end_reached(self, event) -> None:
        QMetaObject.invokeMethod(
            self,
            "_emit_end",
            Qt.ConnectionType.QueuedConnection,
        )

    def _on_error(self, event) -> None:
        QMetaObject.invokeMethod(
            self,
            "_emit_error",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(str, "VLC playback error"),
        )

    # ── Qt slots (main thread) ────────────────────────────────────────────────

    def _emit_position(self, ms: int) -> None:
        self.position_changed.emit(ms)

    def _emit_end(self) -> None:
        self.end_reached.emit()

    def _emit_error(self, msg: str) -> None:
        self.error_occurred.emit(msg)

    # ── Public API ────────────────────────────────────────────────────────────

    def play(self, url: str) -> None:
        if self._player is None:
            logger.error("VLC unavailable — cannot play %s", url)
            self.error_occurred.emit("VLC 未安装，无法播放音频。请安装 VLC: https://www.videolan.org")
            return
        media = self._instance.media_new(url)
        self._player.set_media(media)
        self._player.play()

    def pause(self) -> None:
        if self._player is None:
            return
        self._player.pause()

    def stop(self) -> None:
        if self._player is None:
            return
        self._player.stop()

    def seek(self, position_ms: int) -> None:
        if self._player is None:
            return
        self._player.set_time(position_ms)

    def set_volume(self, volume: int) -> None:
        if self._player is None:
            return
        self._player.audio_set_volume(volume)

    def get_position_ms(self) -> int:
        if self._player is None:
            return 0
        return self._player.get_time()
