import asyncio
import pytest
from PyQt6.QtWidgets import QApplication, QSizePolicy
from PyQt6.QtGui import QColor, QImage
from ui.components.sidebar import SidebarWidget
from ui.components.now_playing_bar import NowPlayingBar
from ui.app_window import MainWindow
from core.models import PlayerState
from ui.theme import COLORS
from ui.pages.settings_page import SettingsPage
from ui.pages.standby_page import StandbyPage
from unittest.mock import MagicMock
from PyQt6.QtCore import QBuffer, QIODevice, QObject, pyqtSignal, Qt


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
    volume_changed = pyqtSignal(int)
    artist_ready = pyqtSignal(object)
    artist_tracks_ready = pyqtSignal(list)
    is_netease_authenticated = False
    is_ytmusic_authenticated = False
    is_spotify_authenticated = False
    display_name = "Somnia"
    background_image_path = ""
    queue_tracks: list = []
    queue_index: int = -1

    def __init__(self):
        super().__init__()
        self.logged_out: list[str] = []

    @property
    def current_state(self):
        from core.models import PlayerState
        return PlayerState()

    def toggle_play_pause(self): pass
    def seek(self, ms): pass
    def set_volume(self, v): self.volume_changed.emit(v)
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
    async def load_artist(self, artist_name, platform): pass
    async def play_prev(self): pass
    async def ensure_netease_auth(self, parent=None): return False
    async def ensure_ytmusic_auth(self, parent=None): return False
    async def ensure_spotify_auth(self, parent=None): return False
    async def logout_netease(self):
        self.logged_out.append("netease")
        self.netease_auth_changed.emit(False)
    async def logout_ytmusic(self):
        self.logged_out.append("ytmusic")
        self.ytmusic_auth_changed.emit(False)
    async def logout_spotify(self):
        self.logged_out.append("spotify")
        self.spotify_auth_changed.emit(False)
    async def get_account_name(self, pid): return ""


def test_sidebar_standby_signal(qapp_instance, qtbot):
    w = SidebarWidget()
    qtbot.addWidget(w)
    w.show()
    with qtbot.waitSignal(w.standby_requested, timeout=500):
        qtbot.mousePress(w._title, Qt.MouseButton.LeftButton)


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


def test_now_playing_cover_rounds_all_corners(qapp_instance, qtbot):
    bar = NowPlayingBar()
    qtbot.addWidget(bar)

    image = QImage(48, 48, QImage.Format.Format_RGB32)
    image.fill(QColor("#ff0000"))
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buffer, "PNG")

    bar.set_cover_pixmap_from_bytes(bytes(buffer.data()))
    rendered = bar._cover.pixmap().toImage().convertToFormat(
        QImage.Format.Format_ARGB32,
    )

    for point in ((0, 0), (47, 0), (0, 47), (47, 47)):
        assert rendered.pixelColor(*point).alpha() == 0
    for point in ((6, 0), (0, 6), (41, 0), (47, 6), (6, 47), (47, 41)):
        assert rendered.pixelColor(*point).alpha() > 0


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


def test_main_window_syncs_volume_between_bar_and_settings(qapp_instance, qtbot):
    ctrl = _MockCtrl()
    w = MainWindow(ctrl)
    qtbot.addWidget(w)

    w.now_playing._volume.setValue(33)
    qapp_instance.processEvents()

    assert w._settings_page._volume_slider.value() == 33
    assert w._settings_page._volume_value.text() == "33"

    w._settings_page._volume_slider.setValue(81)
    qapp_instance.processEvents()

    assert w.now_playing._volume.value() == 81


async def test_settings_logout_requires_confirmation(qapp_instance, qtbot):
    ctrl = _MockCtrl()
    page = SettingsPage(ctrl)
    qtbot.addWidget(page)
    page._set_row_authed("netease", True, "Alice")
    row = page._platform_rows["netease"]

    row["btn"].click()
    await asyncio.sleep(0)

    assert ctrl.logged_out == []
    assert row["btn"].text() == "取消"
    assert not row["confirm_btn"].isHidden()

    row["btn"].click()
    await asyncio.sleep(0)

    assert ctrl.logged_out == []
    assert row["btn"].text() == "退出登录"
    assert row["confirm_btn"].isHidden()

    row["btn"].click()
    row["confirm_btn"].click()
    await asyncio.sleep(0)

    assert ctrl.logged_out == ["netease"]


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


def test_standby_page_creates_hidden(qapp_instance, qtbot):
    ctrl = _MockCtrl()
    # StandbyPage 需要一个有 background_pixmap() 方法的父 widget
    from PyQt6.QtWidgets import QWidget
    from PyQt6.QtGui import QPixmap
    parent_mock = QWidget()
    parent_mock.background_pixmap = lambda: QPixmap()
    qtbot.addWidget(parent_mock)
    page = StandbyPage(ctrl, parent_mock)
    qtbot.addWidget(page)
    assert page.isHidden()
    assert page._close_btn is not None


def test_standby_page_has_left_right_panels(qapp_instance, qtbot):
    ctrl = _MockCtrl()
    from PyQt6.QtWidgets import QWidget
    from PyQt6.QtGui import QPixmap
    parent_mock = QWidget()
    parent_mock.background_pixmap = lambda: QPixmap()
    qtbot.addWidget(parent_mock)
    page = StandbyPage(ctrl, parent_mock)
    qtbot.addWidget(page)
    assert page._title_label is not None
    assert page._artist_label is not None
    assert page._cover_label is not None


def _make_standby(qapp_instance, qtbot) -> "StandbyPage":
    ctrl = _MockCtrl()
    from PyQt6.QtWidgets import QWidget
    from PyQt6.QtGui import QPixmap
    parent_mock = QWidget()
    parent_mock.background_pixmap = lambda: QPixmap()
    qtbot.addWidget(parent_mock)
    page = StandbyPage(ctrl, parent_mock)
    page._parent_ref = parent_mock  # keep parent alive to prevent Qt child deletion
    qtbot.addWidget(page)
    parent_mock.show()
    return page


def test_standby_track_shows_title_and_artist(qapp_instance, qtbot):
    from core.models import Track
    page = _make_standby(qapp_instance, qtbot)
    track = Track(
        id="1", platform="netease", title="远走高飞", artist="金志文",
        artists=["金志文"], album="", album_cover_url="", duration_ms=240000,
    )
    page.on_state_changed(PlayerState(status="playing", current_track=track))
    assert page._title_label.text() == "远走高飞"
    assert page._artist_label.text() == "金志文"


def test_standby_clearing_track_restores_placeholder(qapp_instance, qtbot):
    from core.models import Track
    page = _make_standby(qapp_instance, qtbot)
    track = Track(
        id="1", platform="netease", title="远走高飞", artist="金志文",
        artists=["金志文"], album="", album_cover_url="", duration_ms=240000,
    )
    page.on_state_changed(PlayerState(status="playing", current_track=track))
    page.on_state_changed(PlayerState())   # clear
    assert page._title_label.text() == "暂无播放"
    assert page._artist_label.text() == "—"


def test_standby_set_lyrics_switches_to_lyrics_mode(qapp_instance, qtbot):
    from core.models import LyricLine
    page = _make_standby(qapp_instance, qtbot)
    lines = [
        LyricLine(start_ms=0, end_ms=3000, text="第一行"),
        LyricLine(start_ms=3000, end_ms=6000, text="第二行"),
    ]
    page.set_lyrics(lines)
    assert not page._scroll.isHidden()
    assert page._no_lyrics_label.isHidden()
    assert len(page._line_widgets) == 2


def test_standby_update_position_hidden_no_crash(qapp_instance, qtbot):
    from core.models import LyricLine
    page = _make_standby(qapp_instance, qtbot)
    page.set_lyrics([LyricLine(start_ms=0, end_ms=3000, text="行")])
    # widget is hidden — update_position should silently skip processing
    page.update_position(1500)
    # No exception = pass


def test_standby_set_cover_color_updates_gradient(qapp_instance, qtbot):
    page = _make_standby(qapp_instance, qtbot)
    page.set_cover_color(100, 150, 200)
    assert page._gradient_rgb == (100, 150, 200)


def test_standby_enter_uses_opacity_effect(qapp_instance, qtbot):
    from PyQt6.QtWidgets import QGraphicsOpacityEffect
    page = _make_standby(qapp_instance, qtbot)
    page.enter()
    assert isinstance(page.graphicsEffect(), QGraphicsOpacityEffect)


def test_standby_leave_creates_fade_animation(qapp_instance, qtbot):
    page = _make_standby(qapp_instance, qtbot)
    page.enter()
    page.leave()
    assert page._fade_anim is not None
    qtbot.waitUntil(lambda: page.isHidden(), timeout=1000)


def test_main_window_has_standby_page(qapp_instance, qtbot):
    ctrl = _MockCtrl()
    win = MainWindow(ctrl)
    qtbot.addWidget(win)
    assert hasattr(win, "_standby_page")
    assert isinstance(win._standby_page, StandbyPage)
    assert win._standby_page.isHidden()


def test_main_window_toggle_standby_shows_and_hides(qapp_instance, qtbot):
    ctrl = _MockCtrl()
    win = MainWindow(ctrl)
    qtbot.addWidget(win)
    win._dark_titlebar_done = True
    win.show()
    win._toggle_standby()
    assert win._standby_page.isVisible()
    win._toggle_standby()
    qtbot.waitUntil(lambda: win._standby_page.isHidden(), timeout=1000)
