# tests/test_librespot_backend.py
import pytest
import numpy as np
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication

@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def _make_backend(qapp):
    mock_bridge = MagicMock()
    # Simulate successful load: 1 second of silence at 44100Hz stereo
    audio = np.zeros((44100, 2), dtype="float32")
    mock_bridge.load_track.return_value = (audio, 44100)

    with patch("core.librespot_backend.sd") as mock_sd:
        mock_stream = MagicMock()
        mock_stream.__enter__ = MagicMock(return_value=mock_stream)
        mock_stream.__exit__ = MagicMock(return_value=False)
        mock_sd.OutputStream.return_value = mock_stream

        from core.librespot_backend import LibrespotBackend
        backend = LibrespotBackend(mock_bridge)

    return backend, mock_bridge, mock_sd


def test_initial_position_is_zero(qapp):
    backend, _, _ = _make_backend(qapp)
    assert backend.get_position_ms() == 0


def test_has_session_delegates_to_bridge(qapp):
    backend, mock_bridge, _ = _make_backend(qapp)
    mock_bridge.has_session.return_value = True
    assert backend.has_session() is True


def test_set_volume_clamps(qapp):
    backend, _, _ = _make_backend(qapp)
    backend.set_volume(150)
    assert backend._volume == 1.0
    backend.set_volume(-10)
    assert backend._volume == 0.0
    backend.set_volume(50)
    assert abs(backend._volume - 0.5) < 1e-6


def test_stop_resets_position(qapp):
    backend, _, _ = _make_backend(qapp)
    backend._pos = 44100  # simulate some playback
    backend.stop()
    assert backend.get_position_ms() == 0


def test_seek_updates_seek_pos(qapp):
    backend, _, _ = _make_backend(qapp)
    # Inject fake audio so seek can compute frame offset
    backend._audio_data = np.zeros((88200, 2), dtype="float32")
    backend._samplerate = 44100
    backend.seek(1000)  # seek to 1000ms = 44100 frames
    assert backend._seek_pos == 44100


def test_seek_clamps_to_zero(qapp):
    backend, _, _ = _make_backend(qapp)
    backend._audio_data = np.zeros((44100, 2), dtype="float32")
    backend._samplerate = 44100
    backend.seek(-500)
    assert backend._seek_pos == 0


def test_play_raises_error_when_sd_unavailable(qapp):
    mock_bridge = MagicMock()
    errors = []

    from core.librespot_backend import LibrespotBackend
    with patch("core.librespot_backend.sd", None):
        backend = LibrespotBackend(mock_bridge)
        backend.error_occurred.connect(errors.append)
        backend.play("some_track_id")

    assert len(errors) == 1
    assert "sounddevice" in errors[0].lower()
