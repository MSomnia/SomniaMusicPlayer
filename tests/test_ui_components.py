import pytest
from PyQt6.QtWidgets import QApplication
from ui.components.sidebar import SidebarWidget
from ui.components.now_playing_bar import NowPlayingBar
from ui.app_window import MainWindow
from core.models import PlayerState


@pytest.fixture(scope="session")
def qapp_instance():
    return QApplication.instance() or QApplication([])


def test_sidebar_fixed_width(qapp_instance, qtbot):
    w = SidebarWidget()
    qtbot.addWidget(w)
    assert w.width() == 200


def test_sidebar_nav_signal(qapp_instance, qtbot):
    w = SidebarWidget()
    qtbot.addWidget(w)
    received: list[str] = []
    w.nav_changed.connect(received.append)
    w._nav_buttons["home"].click()
    assert received == ["home"]


def test_sidebar_set_active_checks_correct_button(qapp_instance, qtbot):
    w = SidebarWidget()
    qtbot.addWidget(w)
    w.set_active_page("library")
    assert w._nav_buttons["library"].isChecked()
    assert not w._nav_buttons["home"].isChecked()


def test_now_playing_bar_height(qapp_instance, qtbot):
    bar = NowPlayingBar()
    qtbot.addWidget(bar)
    assert bar.height() == 90


def test_now_playing_bar_play_signal(qapp_instance, qtbot):
    bar = NowPlayingBar()
    qtbot.addWidget(bar)
    with qtbot.waitSignal(bar.play_pause_clicked, timeout=500):
        bar._play_btn.click()


def test_now_playing_bar_update_state_idle(qapp_instance, qtbot):
    bar = NowPlayingBar()
    qtbot.addWidget(bar)
    bar.update_state(PlayerState())
    assert bar._title.text() == "—"
    assert bar._play_btn.text() == "▶"


def test_main_window_title(qapp_instance, qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    assert w.windowTitle() == "SomniaMusicPlayer"


def test_main_window_has_sidebar_and_bar(qapp_instance, qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    assert w.sidebar is not None
    assert w.now_playing is not None
    assert w.content is not None
