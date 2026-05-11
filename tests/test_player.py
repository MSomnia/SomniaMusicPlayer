import pytest
from PyQt6.QtWidgets import QApplication
from core.player import UnifiedPlayer
from core.models import Track


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def _track(**kw) -> Track:
    base = dict(id="t1", platform="netease", title="Test Song",
                artist="Artist", artists=["Artist"], album="Album",
                album_cover_url="", duration_ms=180_000)
    base.update(kw)
    return Track(**base)


def test_initial_state_is_idle(qapp):
    p = UnifiedPlayer()
    assert p.state.status == "idle"
    assert p.state.current_track is None


def test_load_transitions_to_loading(qapp):
    p = UnifiedPlayer()
    t = _track()
    p.load(t)
    assert p.state.status == "loading"
    assert p.state.current_track == t
    assert p.state.duration_ms == 180_000


def test_load_success_transitions_to_playing(qapp):
    p = UnifiedPlayer()
    p.load(_track())
    p.on_load_success()
    assert p.state.status == "playing"


def test_pause_from_idle_is_noop(qapp):
    p = UnifiedPlayer()
    p.pause()
    assert p.state.status == "idle"


def test_pause_from_playing(qapp):
    p = UnifiedPlayer()
    p.load(_track())
    p.on_load_success()
    p.pause()
    assert p.state.status == "paused"


def test_resume_from_paused(qapp):
    p = UnifiedPlayer()
    p.load(_track())
    p.on_load_success()
    p.pause()
    p.resume()
    assert p.state.status == "playing"


def test_stop_returns_to_idle(qapp):
    p = UnifiedPlayer()
    p.load(_track())
    p.on_load_success()
    p.stop()
    assert p.state.status == "idle"
    assert p.state.current_track is None
    assert p.state.position_ms == 0


def test_load_error_transitions_to_error(qapp):
    p = UnifiedPlayer()
    p.load(_track())
    p.on_load_error("network timeout")
    assert p.state.status == "error"


def test_seek_clamps_to_duration(qapp):
    p = UnifiedPlayer()
    p.load(_track(duration_ms=60_000))
    p.on_load_success()
    p.seek(999_999)
    assert p.state.position_ms == 60_000
    p.seek(-100)
    assert p.state.position_ms == 0


def test_seek_ignored_when_idle(qapp):
    p = UnifiedPlayer()
    p.seek(5000)
    assert p.state.position_ms == 0


def test_volume_clamped_to_0_100(qapp):
    p = UnifiedPlayer()
    p.set_volume(150)
    assert p.state.volume == 100
    p.set_volume(-10)
    assert p.state.volume == 0


def test_state_changed_signal_emitted_on_load(qapp, qtbot):
    p = UnifiedPlayer()
    with qtbot.waitSignal(p.state_changed, timeout=500):
        p.load(_track())


def test_track_changed_signal_emitted_on_load(qapp, qtbot):
    p = UnifiedPlayer()
    received = []
    p.track_changed.connect(received.append)
    p.load(_track())
    assert len(received) == 1
    assert received[0].title == "Test Song"
