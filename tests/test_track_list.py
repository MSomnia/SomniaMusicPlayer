import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from core.models import Track
from ui.components.track_list import TrackListWidget


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def _t(tid: str) -> Track:
    return Track(id=tid, platform="netease", title=f"Song {tid}",
                 artist="Artist", artists=["Artist"], album="Alb",
                 album_cover_url="", duration_ms=180_000)


def test_track_list_creates_without_error(qapp, qtbot):
    w = TrackListWidget()
    qtbot.addWidget(w)


def test_set_tracks_populates_list(qapp, qtbot):
    w = TrackListWidget()
    qtbot.addWidget(w)
    w.set_tracks([_t("1"), _t("2"), _t("3")])
    assert w._list.count() == 3



def test_set_tracks_stores_track_in_item(qapp, qtbot):
    w = TrackListWidget()
    qtbot.addWidget(w)
    track = _t("x")
    w.set_tracks([track])
    stored = w._list.item(0).data(Qt.ItemDataRole.UserRole)
    assert stored == track


def test_clear_removes_all_items(qapp, qtbot):
    w = TrackListWidget()
    qtbot.addWidget(w)
    w.set_tracks([_t("1"), _t("2")])
    w.clear()
    assert w._list.count() == 0


def test_show_loading_displays_placeholder(qapp, qtbot):
    w = TrackListWidget()
    qtbot.addWidget(w)
    w.show_loading()
    assert w._list.count() == 0
    assert "搜索" in w._status_label.text() or "加载" in w._status_label.text()


def test_show_empty_displays_message(qapp, qtbot):
    w = TrackListWidget()
    qtbot.addWidget(w)
    w.show_empty("无结果")
    assert "无结果" in w._status_label.text()


def test_track_selected_signal_on_double_click(qapp, qtbot):
    w = TrackListWidget()
    qtbot.addWidget(w)
    w.show()
    track = _t("1")
    w.set_tracks([track])
    received = []
    w.track_selected.connect(received.append)
    # Simulate itemDoubleClicked (mouse simulation unreliable in headless env)
    w._list.itemDoubleClicked.emit(w._list.item(0))
    assert len(received) == 1
    assert received[0] == track
