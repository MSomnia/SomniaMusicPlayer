import pytest
from PyQt6.QtWidgets import QApplication, QSizePolicy
from PyQt6.QtGui import QColor, QImage
from ui.components.sidebar import SidebarWidget
from ui.components.now_playing_bar import NowPlayingBar
from ui.app_window import MainWindow
from core.models import PlayerState
from ui.theme import COLORS
from unittest.mock import MagicMock
from PyQt6.QtCore import QObject, pyqtSignal


class _MockCtrl(QObject):
    state_changed = pyqtSignal(PlayerState)
    position_changed = pyqtSignal(int)
    search_results_ready = pyqtSignal(list)
    netease_auth_changed = pyqtSignal(bool)
    ytmusic_auth_changed = pyqtSignal(bool)
    spotify_auth_changed = pyqtSignal(bool)
    lyrics_ready = pyqtSignal(list)
    cover_color_ready = pyqtSignal(int, int, int)
    cover_art_bytes = pyqtSignal(bytes)
    # Phase 6 signals
    home_sections_ready = pyqtSignal(str, list)
    library_ready = pyqtSignal(str, list)
    album_search_ready = pyqtSignal(str, list)
    queue_changed = pyqtSignal(list, int)
    settings_ready = pyqtSignal(dict)
    profile_changed = pyqtSignal(str)
    background_changed = pyqtSignal(str)
    is_netease_authenticated = False
    is_ytmusic_authenticated = False
    is_spotify_authenticated = False
    display_name = "Somnia"
    background_image_path = ""
    queue_tracks: list = []
    queue_index: int = -1

    def toggle_play_pause(self): pass
    def seek(self, ms): pass
    def set_volume(self, v): pass
    def toggle_shuffle(self): pass
    def cycle_repeat_mode(self): pass
    def add_to_queue(self, track): pass
    def play_queue_tracks(self, tracks, start=0): pass
    def get_cached_home(self, platform): return []
    async def load_settings(self): pass
    async def save_setting(self, key, value):
        if key == "display_name":
            self.display_name = value
            self.profile_changed.emit(value)
        elif key == "background_image_path":
            self.background_image_path = value
            self.background_changed.emit(value)
    async def play_track(self, track): pass
    async def play_next(self): pass
    async def play_prev(self): pass
    async def ensure_netease_auth(self, parent=None): return False
    async def ensure_ytmusic_auth(self, parent=None): return False
    async def ensure_spotify_auth(self, parent=None): return False


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


def test_sidebar_title_uses_greeting_and_display_name(qapp_instance, qtbot):
    w = SidebarWidget()
    qtbot.addWidget(w)
    w.set_display_name("阿眠")
    assert w._title.text() in {
        "早安，阿眠",
        "午安，阿眠",
        "晚安，阿眠",
    }


def test_now_playing_bar_height(qapp_instance, qtbot):
    bar = NowPlayingBar()
    qtbot.addWidget(bar)
    assert bar.height() == 90
    assert bar.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert bar.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Fixed


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


def test_now_playing_bar_primary_buttons_are_visible(qapp_instance, qtbot):
    bar = NowPlayingBar()
    qtbot.addWidget(bar)
    bar.resize(900, 90)
    bar.show()
    qapp_instance.processEvents()

    image = bar.grab().toImage()

    play_top_left = bar._play_btn.mapTo(bar, bar._play_btn.rect().topLeft())
    play_rect = bar._play_btn.rect().translated(play_top_left)
    accent_pixels = 0
    for x in range(play_rect.left(), play_rect.right() + 1):
        for y in range(play_rect.top(), play_rect.bottom() + 1):
            if image.pixelColor(x, y).name().lower() == COLORS["accent"].lower():
                accent_pixels += 1

    lyrics_top_left = bar._lyrics_btn.mapTo(bar, bar._lyrics_btn.rect().topLeft())
    lyrics_rect = bar._lyrics_btn.rect().translated(lyrics_top_left)
    visible_text_pixels = 0
    for x in range(lyrics_rect.left(), lyrics_rect.right() + 1):
        for y in range(lyrics_rect.top(), lyrics_rect.bottom() + 1):
            color = image.pixelColor(x, y)
            if color.red() >= 100 and color.green() >= 100 and color.blue() >= 100:
                visible_text_pixels += 1

    assert accent_pixels > 100
    assert visible_text_pixels > 10


def test_main_window_title(qapp_instance, qtbot):
    w = MainWindow(_MockCtrl())
    qtbot.addWidget(w)
    assert w.windowTitle() == "SomniaMusicPlayer"


def test_main_window_has_sidebar_and_bar(qapp_instance, qtbot):
    w = MainWindow(_MockCtrl())
    qtbot.addWidget(w)
    assert w.sidebar is not None
    assert w.now_playing is not None
    assert w.content is not None


def test_main_window_uses_black_gaps_around_sidebar_and_content(qapp_instance, qtbot):
    w = MainWindow(_MockCtrl())
    qtbot.addWidget(w)
    w.resize(1000, 700)
    w._dark_titlebar_done = True
    w.show()
    qapp_instance.processEvents()

    assert w.sidebar.x() == 12
    assert w.content.x() - (w.sidebar.x() + w.sidebar.width()) == 12
    assert w.centralWidget().width() - (w.content.x() + w.content.width()) == 12

    image = w.grab().toImage()
    gap_x = w.sidebar.x() + w.sidebar.width() + 6
    gap_y = w.sidebar.y() + 8
    sidebar_x = w.sidebar.x() + 8
    content_x = w.content.x() + 8

    assert image.pixelColor(6, gap_y).name().lower() == "#000000"
    assert image.pixelColor(gap_x, gap_y).name().lower() == "#000000"
    assert image.pixelColor(w.width() - 6, gap_y).name().lower() == "#000000"
    assert image.pixelColor(w.sidebar.x(), w.sidebar.y()).name().lower() == "#000000"
    assert image.pixelColor(w.content.x(), w.content.y()).name().lower() == "#000000"
    assert image.pixelColor(sidebar_x, gap_y).name().lower() == COLORS["bg_panel"].lower()
    assert image.pixelColor(content_x, gap_y).name().lower() == COLORS["bg_panel"].lower()
    assert image.pixelColor(content_x, w.content.y() + 200).name().lower() == COLORS["bg_panel"].lower()


def test_main_window_uses_custom_background_image(qapp_instance, qtbot, tmp_path):
    image_path = tmp_path / "background.png"
    image = QImage(4, 4, QImage.Format.Format_RGB32)
    image.fill(QColor("#7a1234"))
    assert image.save(str(image_path))

    ctrl = _MockCtrl()
    ctrl.background_image_path = str(image_path)
    w = MainWindow(ctrl)
    qtbot.addWidget(w)
    w.resize(1000, 700)
    w._dark_titlebar_done = True
    w.show()
    qapp_instance.processEvents()

    rendered = w.grab().toImage()
    assert rendered.pixelColor(6, 20).name().lower() == "#7a1234"
    assert rendered.pixelColor(
        w.sidebar.x() + 20,
        w.sidebar.y() + 20,
    ).name().lower() != COLORS["bg_panel"].lower()
    assert rendered.pixelColor(
        w.content.x() + 20,
        w.content.y() + 200,
    ).name().lower() != COLORS["bg_panel"].lower()


def test_now_playing_bar_fills_window_width(qapp_instance, qtbot):
    w = MainWindow(_MockCtrl())
    qtbot.addWidget(w)
    w.resize(1000, 700)
    w._dark_titlebar_done = True
    w.show()
    qapp_instance.processEvents()

    assert w.now_playing.x() == 0
    assert w.now_playing.width() == w.centralWidget().width()

    image = w.now_playing.grab().toImage()
    leaked_panel_pixels = 0
    for x in range(image.width()):
        for y in range(image.height()):
            if image.pixelColor(x, y).name().lower() == COLORS["bg_panel"].lower():
                leaked_panel_pixels += 1

    assert leaked_panel_pixels < 50


def test_lyrics_page_preserves_content_rounding(qapp_instance, qtbot):
    w = MainWindow(_MockCtrl())
    qtbot.addWidget(w)
    w.resize(1000, 700)
    w._dark_titlebar_done = True
    w.show()
    w.content.setCurrentIndex(w._page_map["lyrics"])
    qapp_instance.processEvents()

    image = w.grab().toImage()

    assert image.pixelColor(w.content.x(), w.content.y()).name().lower() == "#000000"
    assert image.pixelColor(w.content.x() + 8, w.content.y() + 8).name().lower() == COLORS["bg_base"].lower()


def test_sidebar_has_platform_login_requested_signal(qapp_instance, qtbot):
    w = SidebarWidget()
    qtbot.addWidget(w)
    received = []
    w.platform_login_requested.connect(received.append)
    w._platform_buttons["netease"].click()
    assert received == ["netease"]


def test_sidebar_set_platform_status_logged_in(qapp_instance, qtbot):
    w = SidebarWidget()
    qtbot.addWidget(w)
    w.set_platform_status("netease", True)
    assert "●" in w._platform_buttons["netease"].text()


def test_sidebar_set_platform_status_logged_out(qapp_instance, qtbot):
    w = SidebarWidget()
    qtbot.addWidget(w)
    w.set_platform_status("netease", True)
    w.set_platform_status("netease", False)
    assert "○" in w._platform_buttons["netease"].text()
