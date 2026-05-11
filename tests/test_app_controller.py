import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication
from core.models import Track, PlayerState


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def _track(**kw) -> Track:
    base = dict(id="t1", platform="netease", title="Song", artist="A",
                artists=["A"], album="Alb", album_cover_url="", duration_ms=180_000)
    base.update(kw)
    return Track(**base)


class _FakeVLC(QObject):
    """Test double for VLCBackend — real Qt signals, no libvlc needed."""
    position_changed = pyqtSignal(int)
    end_reached = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def play(self, url): self._last_url = url
    def pause(self): pass
    def stop(self): pass
    def seek(self, ms): pass
    def set_volume(self, v): pass
    def get_position_ms(self): return 0


@pytest.fixture
def fake_vlc(qapp):
    return _FakeVLC()


@pytest.fixture
def ctrl(qapp, fake_vlc):
    with patch("core.app_controller.VLCBackend", return_value=fake_vlc), \
         patch("core.app_controller.AppRepository") as MockRepo:
        mock_repo = AsyncMock()
        mock_repo.get_setting = AsyncMock(return_value="70")
        mock_repo.load_credential = AsyncMock(return_value=None)
        mock_repo.save_credential = AsyncMock()
        mock_repo.init = AsyncMock()
        mock_repo.close = AsyncMock()
        MockRepo.return_value = mock_repo

        from core.app_controller import AppController
        c = AppController()
        c._vlc = fake_vlc
        return c


async def test_init_without_saved_cookies_stays_unauthenticated(ctrl):
    ctrl._repo.load_credential = AsyncMock(return_value=None)
    received = []
    ctrl.netease_auth_changed.connect(received.append)
    await ctrl.init()
    assert ctrl._client is None
    assert received == []


async def test_init_with_saved_cookies_builds_client(ctrl):
    ctrl._repo.load_credential = AsyncMock(
        return_value={"MUSIC_U": "abc", "__csrf": "xyz"}
    )
    received = []
    ctrl.netease_auth_changed.connect(received.append)
    await ctrl.init()
    assert ctrl._client is not None
    assert received == [True]


async def test_play_track_calls_vlc_play(ctrl, fake_vlc):
    mock_client = MagicMock()
    mock_client.get_stream_url = AsyncMock(return_value="https://cdn.example.com/a.mp3")
    ctrl._client = mock_client

    t = _track()
    await ctrl.play_track(t)

    mock_client.get_stream_url.assert_awaited_once_with(t)
    assert hasattr(fake_vlc, "_last_url")
    assert fake_vlc._last_url == "https://cdn.example.com/a.mp3"
    assert ctrl._player.state.status == "playing"


async def test_play_track_error_sets_error_state(ctrl):
    mock_client = MagicMock()
    mock_client.get_stream_url = AsyncMock(side_effect=RuntimeError("timeout"))
    ctrl._client = mock_client

    await ctrl.play_track(_track())
    assert ctrl._player.state.status == "error"


async def test_toggle_play_pause_from_playing(ctrl, fake_vlc):
    mock_client = MagicMock()
    mock_client.get_stream_url = AsyncMock(return_value="https://cdn.example.com/a.mp3")
    ctrl._client = mock_client
    await ctrl.play_track(_track())

    assert ctrl._player.state.status == "playing"
    ctrl.toggle_play_pause()
    assert ctrl._player.state.status == "paused"


async def test_toggle_play_pause_from_paused_resumes(ctrl, fake_vlc):
    mock_client = MagicMock()
    mock_client.get_stream_url = AsyncMock(return_value="https://cdn.example.com/a.mp3")
    ctrl._client = mock_client
    await ctrl.play_track(_track())
    ctrl.toggle_play_pause()   # → paused
    ctrl.toggle_play_pause()   # → playing
    assert ctrl._player.state.status == "playing"


async def test_play_next_stops_when_queue_exhausted(ctrl, fake_vlc):
    mock_client = MagicMock()
    mock_client.get_stream_url = AsyncMock(return_value="https://cdn.example.com/a.mp3")
    ctrl._client = mock_client
    await ctrl.play_track(_track())   # queue=[t], index=0

    # next() with repeat_mode="none" returns None → stop
    await ctrl.play_next()
    assert ctrl._player.state.status == "idle"


async def test_search_emits_results(ctrl):
    mock_client = MagicMock()
    tracks = [_track(id="1"), _track(id="2")]
    mock_client.search = AsyncMock(return_value=tracks)
    ctrl._client = mock_client

    received = []
    ctrl.search_results_ready.connect(received.append)
    result = await ctrl.search("test")

    assert result == tracks
    assert len(received) == 1
    assert received[0] == tracks


async def test_search_returns_empty_when_not_authenticated(ctrl):
    ctrl._client = None
    result = await ctrl.search("test")
    assert result == []


async def test_is_netease_authenticated_property(ctrl):
    assert ctrl.is_netease_authenticated is False
    ctrl._client = MagicMock()
    assert ctrl.is_netease_authenticated is True
