# core/librespot_backend.py
from __future__ import annotations
import logging
import threading
import time

import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal, QMetaObject, Qt, Q_ARG, pyqtSlot

logger = logging.getLogger(__name__)

try:
    import sounddevice as sd
except Exception as _sd_err:
    sd = None  # type: ignore[assignment]
    logger.warning(
        "sounddevice unavailable: %s — Spotify audio disabled. "
        "Install via: pip install sounddevice",
        _sd_err,
    )


class LibrespotBackend(QObject):
    """PCM playback backend for Spotify via librespot-python + sounddevice.

    Interface mirrors VLCBackend so AppController can treat both uniformly.
    Playback runs in a daemon thread; Qt signals are emitted via invokeMethod.
    """

    position_changed = pyqtSignal(int)   # ms
    end_reached = pyqtSignal()
    error_occurred = pyqtSignal(str)
    playback_started = pyqtSignal()

    _BLOCK_SIZE = 1024   # frames per sounddevice write
    _REPORT_MS = 250     # position-report interval

    def __init__(self, bridge, parent=None) -> None:
        super().__init__(parent)
        self._bridge = bridge
        self._thread: threading.Thread | None = None
        self._audio_data: np.ndarray | None = None
        self._samplerate: int = 44100
        self._pos: int = 0
        self._volume: float = 0.7
        self._paused = threading.Event()
        self._stopped = threading.Event()
        self._seek_pos: int | None = None
        self._lock = threading.Lock()

    # ── public API (mirrors VLCBackend) ───────────────────────────────────────

    def has_session(self) -> bool:
        return self._bridge.has_session()

    def play(self, track_id: str) -> None:
        if sd is None:
            self.error_occurred.emit(
                "sounddevice 未安装，无法播放 Spotify 音频。请运行: pip install sounddevice"
            )
            return
        self.stop()
        self._stopped.clear()
        self._paused.clear()
        self._pos = 0
        self._thread = threading.Thread(
            target=self._load_and_play, args=(track_id,), daemon=True
        )
        self._thread.start()

    def pause(self) -> None:
        self._paused.set()

    def resume(self) -> None:
        self._paused.clear()

    def stop(self) -> None:
        self._stopped.set()
        self._paused.clear()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        self._pos = 0

    def seek(self, position_ms: int) -> None:
        if self._audio_data is None:
            return
        frame = int(position_ms * self._samplerate / 1000)
        with self._lock:
            self._seek_pos = max(0, min(frame, len(self._audio_data) - 1))

    def set_volume(self, volume: int) -> None:
        self._volume = max(0.0, min(volume / 100.0, 1.0))

    def get_position_ms(self) -> int:
        return int(self._pos / max(self._samplerate, 1) * 1000)

    # ── background thread ─────────────────────────────────────────────────────

    def _load_and_play(self, track_id: str) -> None:
        try:
            audio_data, samplerate = self._bridge.load_track(track_id)
        except Exception as exc:
            logger.error("Librespot load failed for %s: %s", track_id, exc)
            QMetaObject.invokeMethod(
                self, "_emit_error",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(str, str(exc)),
            )
            return

        self._audio_data = audio_data
        self._samplerate = samplerate
        channels = audio_data.shape[1] if audio_data.ndim > 1 else 1

        QMetaObject.invokeMethod(
            self, "_emit_playback_started", Qt.ConnectionType.QueuedConnection
        )

        try:
            with sd.OutputStream(
                samplerate=samplerate,
                channels=channels,
                dtype="float32",
            ) as stream:
                self._pump(stream)
        except Exception as exc:
            logger.error("sounddevice stream error: %s", exc)
            if not self._stopped.is_set():
                QMetaObject.invokeMethod(
                    self, "_emit_error",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, str(exc)),
                )
            return

        if not self._stopped.is_set():
            QMetaObject.invokeMethod(
                self, "_emit_end", Qt.ConnectionType.QueuedConnection
            )

    def _pump(self, stream: "sd.OutputStream") -> None:
        total = len(self._audio_data)
        last_report_ms = -self._REPORT_MS

        while not self._stopped.is_set():
            if self._paused.is_set():
                time.sleep(0.02)
                continue

            with self._lock:
                if self._seek_pos is not None:
                    self._pos = self._seek_pos
                    self._seek_pos = None

            end = self._pos + self._BLOCK_SIZE
            block = self._audio_data[self._pos:end]

            if len(block) == 0:
                break

            # Apply software volume
            block = block * self._volume

            # Pad last block so sounddevice gets a full buffer
            if len(block) < self._BLOCK_SIZE:
                pad = self._BLOCK_SIZE - len(block)
                block = np.pad(block, ((0, pad), (0, 0)))

            stream.write(block)
            self._pos = min(end, total)

            now_ms = int(self._pos / self._samplerate * 1000)
            if now_ms - last_report_ms >= self._REPORT_MS:
                last_report_ms = now_ms
                QMetaObject.invokeMethod(
                    self, "_emit_position",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(int, now_ms),
                )

    # ── Qt slots (main thread) ────────────────────────────────────────────────

    @pyqtSlot()
    def _emit_playback_started(self) -> None:
        self.playback_started.emit()

    @pyqtSlot()
    def _emit_end(self) -> None:
        self.end_reached.emit()

    @pyqtSlot(str)
    def _emit_error(self, msg: str) -> None:
        self.error_occurred.emit(msg)

    @pyqtSlot(int)
    def _emit_position(self, ms: int) -> None:
        self.position_changed.emit(ms)
