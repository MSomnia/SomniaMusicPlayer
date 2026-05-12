import io
import pytest
import numpy as np
from pathlib import Path
from unittest.mock import MagicMock, patch


def _make_bridge(tmp_path):
    creds_path = str(tmp_path / "spotify_credentials.json")
    from platforms.spotify.librespot_bridge import LibrespotBridge
    return LibrespotBridge(creds_path), creds_path


def test_has_session_false_initially(tmp_path):
    bridge, _ = _make_bridge(tmp_path)
    assert bridge.has_session() is False


def test_load_track_raises_without_session(tmp_path):
    bridge, _ = _make_bridge(tmp_path)
    with pytest.raises(RuntimeError, match="No session"):
        bridge.load_track("4iV5W9uYEdYUVa79Axb7Rh")


def test_load_track_returns_numpy_array(tmp_path):
    bridge, _ = _make_bridge(tmp_path)

    fake_audio = np.zeros((44100, 2), dtype="float32")
    mock_session = MagicMock()
    bridge._session = mock_session

    mock_loaded = MagicMock()
    mock_audio_stream = MagicMock()
    mock_audio_stream.read.side_effect = [b"fake_ogg_bytes", b""]
    mock_loaded.input_stream.stream.return_value = mock_audio_stream
    mock_session.content_feeder.return_value.load.return_value = mock_loaded

    with patch("platforms.spotify.librespot_bridge.sf.SoundFile") as mock_sf_cls:
        mock_sf = MagicMock()
        mock_sf.__enter__ = MagicMock(return_value=mock_sf)
        mock_sf.__exit__ = MagicMock(return_value=False)
        mock_sf.samplerate = 44100
        mock_sf.read.return_value = fake_audio
        mock_sf_cls.return_value = mock_sf

        data, sr = bridge.load_track("4iV5W9uYEdYUVa79Axb7Rh")

    assert sr == 44100
    assert data.shape == (44100, 2)


def test_close_clears_session(tmp_path):
    bridge, _ = _make_bridge(tmp_path)
    mock_session = MagicMock()
    bridge._session = mock_session

    bridge.close()

    mock_session.close.assert_called_once()
    assert bridge.has_session() is False
