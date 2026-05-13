from __future__ import annotations
import logging
from PyQt6.QtCore import QObject, pyqtSignal, QTimer, pyqtSlot, QMetaObject, Qt, Q_ARG

logger = logging.getLogger(__name__)

try:
    import vlc
except Exception as _vlc_err:
    vlc = None  # type: ignore[assignment]
    logger.warning(
        "python-vlc could not load libvlc: %s — audio playback disabled. "
        "Install VLC: https://www.videolan.org",
        _vlc_err,
    )


class VLCBackend(QObject):
    """python-vlc wrapper.

    Position is polled via a QTimer running on the main thread (250 ms) to
    avoid the thread-safety pitfalls of invoking Qt slots from VLC's internal
    callback threads.  End-reached and error events still use the VLC event
    manager, marshalled back through invokeMethod with proper @pyqtSlot
    decorators so Qt's meta-object system can find them.
    """

    position_changed = pyqtSignal(int)   # ms
    duration_changed = pyqtSignal(int)   # ms — emitted once when VLC reports a non-zero length
    end_reached = pyqtSignal()
    error_occurred = pyqtSignal(str)

    _POLL_MS = 250  # position poll interval

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        if vlc is None:
            self._instance = None
            self._player = None
        else:
            self._instance = vlc.Instance("--no-xlib")
            self._player = self._instance.media_player_new()
            self._wire_events()

        # Main-thread timer for position polling — no cross-thread signal needed
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(self._POLL_MS)
        self._poll_timer.timeout.connect(self._on_poll)

        self._last_ended = False  # debounce end-reached from polling
        self._reported_duration: int = 0  # last duration emitted via duration_changed

    def _wire_events(self) -> None:
        em = self._player.event_manager()
        em.event_attach(vlc.EventType.MediaPlayerEndReached, self._on_end_reached)
        em.event_attach(vlc.EventType.MediaPlayerEncounteredError, self._on_error)

    # ── VLC event callbacks (VLC background thread) ───────────────────────────

    def _on_end_reached(self, event) -> None:
        QMetaObject.invokeMethod(self, "_emit_end", Qt.ConnectionType.QueuedConnection)

    def _on_error(self, event) -> None:
        QMetaObject.invokeMethod(
            self, "_emit_error",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(str, "VLC playback error"),
        )

    # ── Qt slots (main thread) ────────────────────────────────────────────────

    @pyqtSlot()
    def _on_poll(self) -> None:
        """Called by the main-thread timer; safe to emit Qt signals here."""
        if self._player is None:
            return
        ms = self._player.get_time()
        if isinstance(ms, int) and ms >= 0:
            self.position_changed.emit(ms)
        # Emit duration once when VLC first reports a non-zero length.
        # This fills in duration_ms=0 tracks (e.g. ytmusic home page items).
        length = self._player.get_length()
        if isinstance(length, int) and length > 0 and length != self._reported_duration:
            self._reported_duration = length
            self.duration_changed.emit(length)

    @pyqtSlot()
    def _emit_end(self) -> None:
        self._poll_timer.stop()
        self.end_reached.emit()

    @pyqtSlot(str)
    def _emit_error(self, msg: str) -> None:
        self._poll_timer.stop()
        self.error_occurred.emit(msg)

    # ── Public API ────────────────────────────────────────────────────────────

    def play(self, url: str, vlc_options: list[str] | None = None) -> None:
        if self._player is None:
            logger.error("VLC unavailable — cannot play %s", url)
            self.error_occurred.emit(
                "VLC 未安装，无法播放音频。请安装 VLC: https://www.videolan.org"
            )
            return
        self._last_ended = False
        self._reported_duration = 0
        media = self._instance.media_new(url)
        for opt in (vlc_options or []):
            media.add_option(opt)
        self._player.set_media(media)
        self._player.play()
        self._poll_timer.start()

    def pause(self) -> None:
        if self._player is None:
            return
        self._player.pause()

    def stop(self) -> None:
        if self._player is None:
            return
        self._poll_timer.stop()
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
