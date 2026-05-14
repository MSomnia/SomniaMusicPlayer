import pytest
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton
from PyQt6.QtCore import Qt
from ui.components.playlist_picker_popup import PlaylistPickerPopup
from core.models import Playlist


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def _make_popup(qapp, qtbot, platform="spotify"):
    p = PlaylistPickerPopup(platform)
    qtbot.addWidget(p)
    p.show()
    return p


def test_initial_shows_loading(qapp, qtbot):
    p = _make_popup(qapp, qtbot)
    loading = p.findChild(QLabel, "loading_lbl")
    assert loading is not None
    assert loading.isVisible()
    assert "加载歌单中" in loading.text()


def test_title_contains_platform_label(qapp, qtbot):
    p = _make_popup(qapp, qtbot, platform="spotify")
    title = p.findChild(QLabel, "title_lbl")
    assert title is not None
    assert "Spotify" in title.text()


def test_title_netease(qapp, qtbot):
    p = _make_popup(qapp, qtbot, platform="netease")
    title = p.findChild(QLabel, "title_lbl")
    assert "网易云音乐" in title.text()


def test_title_ytmusic(qapp, qtbot):
    p = _make_popup(qapp, qtbot, platform="ytmusic")
    title = p.findChild(QLabel, "title_lbl")
    assert "YouTube Music" in title.text()


def _make_playlist(name="我的歌单", track_count=10):
    return Playlist(id="p1", platform="spotify", name=name,
                    cover_url="", track_count=track_count)


def test_set_playlists_hides_loading(qapp, qtbot):
    p = _make_popup(qapp, qtbot)
    p.set_playlists([_make_playlist()])
    loading = p.findChild(QLabel, "loading_lbl")
    assert not loading.isVisible()


def test_set_playlists_shows_buttons(qapp, qtbot):
    p = _make_popup(qapp, qtbot)
    playlists = [_make_playlist("歌单A", 5), _make_playlist("歌单B", 0)]
    p.set_playlists(playlists)
    btns = p.findChildren(QPushButton)
    labels = [b.text() for b in btns]
    assert any("歌单A" in t and "5首" in t for t in labels)
    assert any("歌单B" in t for t in labels)


def test_set_playlists_empty_shows_no_playlist_message(qapp, qtbot):
    p = _make_popup(qapp, qtbot)
    p.set_playlists([])
    labels = [l.text() for l in p.findChildren(QLabel)]
    assert any("没有可加入的歌单" in t for t in labels)


def test_set_error_updates_loading_label(qapp, qtbot):
    p = _make_popup(qapp, qtbot)
    p.set_error("获取歌单失败")
    loading = p.findChild(QLabel, "loading_lbl")
    assert loading.isVisible()
    assert "获取歌单失败" in loading.text()


def test_playlist_selected_signal(qapp, qtbot):
    p = _make_popup(qapp, qtbot)
    pl = _make_playlist("测试歌单")
    p.set_playlists([pl])
    received = []
    p.playlist_selected.connect(received.append)
    btns = p.findChildren(QPushButton)
    target = next(b for b in btns if "测试歌单" in b.text())
    target.click()
    assert received == [pl]


def test_set_playlists_noop_when_not_visible(qapp, qtbot):
    p = PlaylistPickerPopup("spotify")
    qtbot.addWidget(p)
    # Not shown → set_playlists should silently do nothing
    p.set_playlists([_make_playlist()])
    # isVisibleTo checks visibility relative to parent (not screen),
    # so loading_lbl should still be "enabled" (not hidden by setVisible(False))
    loading = p.findChild(QLabel, "loading_lbl")
    assert loading.isVisibleTo(p)
    # scroll area should still be hidden relative to parent
    assert not p._scroll.isVisibleTo(p)
