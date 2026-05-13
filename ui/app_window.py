from __future__ import annotations
import asyncio
import ctypes
import ctypes.util
import logging
import sys
import time
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget, QLabel,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter, QPixmap
from ui.theme import COLORS, FONTS
from ui.frosted import paint_frosted_panel
from ui.components.sidebar import SidebarWidget
from ui.components.now_playing_bar import NowPlayingBar
from ui.components.lyrics_view import LyricsView
from ui.components.queue_panel import QueuePanel
from ui.pages.search_page import SearchPage
from ui.pages.home_page import HomePage
from ui.pages.library_page import LibraryPage
from ui.pages.settings_page import SettingsPage

logger = logging.getLogger(__name__)


class _ErrorToast(QLabel):
    """Transient overlay that shows '歌曲无法播放' and auto-hides after 3 s."""

    _DURATION_MS = 3000

    def __init__(self, parent: QWidget) -> None:
        super().__init__("  ✕  歌曲无法播放  ", parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(40)
        self.hide()
        c, f = COLORS, FONTS
        self.setStyleSheet(f"""
            _ErrorToast, QLabel {{
                background-color: {c['bg_elevated']};
                border: 1px solid #FF4444;
                border-radius: 8px;
                color: #FF6B6B;
                font-size: {f['size_sm']}px;
                font-weight: bold;
            }}
        """)

    def popup(self) -> None:
        p = self.parent()
        w = 220
        self.setGeometry((p.width() - w) // 2, 20, w, 40)
        self.show()
        self.raise_()
        QTimer.singleShot(self._DURATION_MS, self.hide)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if self.isVisible():
            p = self.parent()
            self.move((p.width() - self.width()) // 2, 20)


class _AppRoot(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("appRoot")
        self.setAutoFillBackground(False)
        self._background_path = ""
        self._background_pixmap = QPixmap()

    def set_background_image(self, path: str) -> None:
        path = path.strip()
        self._background_path = path
        self._background_pixmap = QPixmap(path) if path else QPixmap()
        self.update()
        for child in self.findChildren(QWidget):
            child.update()

    def background_pixmap(self) -> QPixmap:
        return self._background_pixmap

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        if self._background_pixmap.isNull():
            return

        source = self._background_pixmap
        scaled = source.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)


class _FrostedStackedWidget(QStackedWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("contentArea")
        self.setAutoFillBackground(False)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        paint_frosted_panel(self, painter)
        super().paintEvent(event)


def _apply_dark_titlebar(win_id: int) -> None:
    """Force the macOS native titlebar/traffic-lights to dark appearance.

    Uses ctypes to call the Objective-C runtime directly so no PyObjC
    dependency is required beyond what macOS ships natively.
    """
    if sys.platform != "darwin":
        return
    try:
        objc_lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))

        objc_lib.objc_getClass.restype = ctypes.c_void_p
        objc_lib.objc_getClass.argtypes = [ctypes.c_char_p]
        objc_lib.sel_registerName.restype = ctypes.c_void_p
        objc_lib.sel_registerName.argtypes = [ctypes.c_char_p]

        def _sel(name: bytes) -> ctypes.c_void_p:
            return objc_lib.sel_registerName(name)

        def _send(receiver, selector: bytes, *args,
                  restype=ctypes.c_void_p, argtypes: list | None = None):
            objc_lib.objc_msgSend.restype = restype
            objc_lib.objc_msgSend.argtypes = (
                [ctypes.c_void_p, ctypes.c_void_p] + (argtypes or [])
            )
            return objc_lib.objc_msgSend(receiver, _sel(selector), *args)

        # NSView (Qt winId) → NSWindow
        ns_view = ctypes.c_void_p(win_id)
        ns_window = _send(ns_view, b"window")

        # Build NSString for the appearance name
        NSString = objc_lib.objc_getClass(b"NSString")
        name_str = _send(
            NSString, b"stringWithUTF8String:",
            b"NSAppearanceNameDarkAqua",
            argtypes=[ctypes.c_char_p],
        )

        # NSAppearance.appearanceNamed_(name)
        NSAppearance = objc_lib.objc_getClass(b"NSAppearance")
        dark_appearance = _send(
            NSAppearance, b"appearanceNamed:",
            name_str,
            argtypes=[ctypes.c_void_p],
        )

        # [window setAppearance:dark_appearance]
        _send(
            ns_window, b"setAppearance:",
            dark_appearance,
            restype=None,
            argtypes=[ctypes.c_void_p],
        )
    except Exception as exc:
        logger.debug("Dark titlebar unavailable: %s", exc)


class MainWindow(QMainWindow):
    def __init__(self, ctrl) -> None:
        super().__init__()
        self._ctrl = ctrl
        self.setWindowTitle("SomniaMusicPlayer")
        self.setMinimumSize(900, 600)
        self._setup_ui()
        self._apply_styles()
        self._wire_signals()
        self.sidebar.set_active_page("home")
        self._dark_titlebar_done = False

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._dark_titlebar_done:
            self._dark_titlebar_done = True
            _apply_dark_titlebar(int(self.winId()))

    def _setup_ui(self) -> None:
        central = _AppRoot()
        self._app_root = central
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        body = QHBoxLayout()
        body.setContentsMargins(12, 12, 12, 12)
        body.setSpacing(12)

        self.sidebar = SidebarWidget()
        self.sidebar.nav_changed.connect(self._on_nav)
        self.sidebar.platform_login_requested.connect(self._on_platform_login)
        body.addWidget(self.sidebar)

        self.content = _FrostedStackedWidget()

        self._home_page = HomePage(self._ctrl)
        self._search_page = SearchPage(self._ctrl)
        self._library_page = LibraryPage(self._ctrl)
        self._settings_page = SettingsPage(self._ctrl)
        self._lyrics_view = LyricsView()

        self._page_map: dict[str, int] = {
            "home":     self.content.addWidget(self._home_page),
            "search":   self.content.addWidget(self._search_page),
            "library":  self.content.addWidget(self._library_page),
            "settings": self.content.addWidget(self._settings_page),
            "lyrics":   self.content.addWidget(self._lyrics_view),
        }
        self._prev_page: str = "home"

        body.addWidget(self.content, stretch=1)
        root.addLayout(body, stretch=1)

        self.now_playing = NowPlayingBar()
        root.addWidget(self.now_playing)

        # Queue panel (lazy-created popup)
        self._queue_panel: QueuePanel | None = None

        # Error toast — child of central so it overlays the content area
        self._error_toast = _ErrorToast(central)
        self._last_error_skip: float = 0.0  # guard against rapid cascades

    def _wire_signals(self) -> None:
        ctrl = self._ctrl

        # Player state → UI
        ctrl.state_changed.connect(self.now_playing.update_state)
        ctrl.state_changed.connect(self._on_state_changed)
        ctrl.position_changed.connect(self.now_playing.update_position)
        ctrl.position_changed.connect(self._lyrics_view.update_position)

        # Auth status → sidebar
        ctrl.netease_auth_changed.connect(
            lambda ok: self.sidebar.set_platform_status("netease", ok)
        )
        ctrl.ytmusic_auth_changed.connect(
            lambda ok: self.sidebar.set_platform_status("ytmusic", ok)
        )
        ctrl.spotify_auth_changed.connect(
            lambda ok: self.sidebar.set_platform_status("spotify", ok)
        )
        ctrl.profile_changed.connect(self.sidebar.set_display_name)
        ctrl.background_changed.connect(self._app_root.set_background_image)

        # Lyrics & cover
        ctrl.lyrics_ready.connect(self._lyrics_view.set_lyrics)
        ctrl.cover_color_ready.connect(self._lyrics_view.set_cover_color)
        ctrl.cover_art_bytes.connect(self._lyrics_view.set_cover_art_bytes)
        ctrl.cover_art_bytes.connect(self.now_playing.set_cover_pixmap_from_bytes)

        # Sync initial auth state (ctrl.init() runs before MainWindow is built)
        self.sidebar.set_platform_status("netease", ctrl.is_netease_authenticated)
        self.sidebar.set_platform_status("ytmusic", ctrl.is_ytmusic_authenticated)
        self.sidebar.set_platform_status("spotify", ctrl.is_spotify_authenticated)
        self.sidebar.set_display_name(getattr(ctrl, "display_name", "Somnia"))
        self._app_root.set_background_image(
            getattr(ctrl, "background_image_path", "")
        )

        # Playback controls
        self.now_playing.play_pause_clicked.connect(ctrl.toggle_play_pause)
        self.now_playing.seek_requested.connect(ctrl.seek)
        self.now_playing.next_clicked.connect(
            lambda: asyncio.ensure_future(ctrl.play_next())
        )
        self.now_playing.prev_clicked.connect(
            lambda: asyncio.ensure_future(ctrl.play_prev())
        )
        self.now_playing.volume_changed.connect(ctrl.set_volume)
        self.now_playing.shuffle_toggled.connect(ctrl.toggle_shuffle)
        self.now_playing.repeat_toggled.connect(ctrl.cycle_repeat_mode)

        # Lyrics & queue toggle
        self.now_playing.lyrics_toggled.connect(self._toggle_lyrics)
        self.now_playing.track_info_clicked.connect(self._show_lyrics)
        self.now_playing.queue_requested.connect(self._show_queue)
        self._lyrics_view.back_requested.connect(self._toggle_lyrics)

    # ── state handlers ────────────────────────────────────────────────────────

    def _on_state_changed(self, state) -> None:
        if state.current_track is None:
            self._lyrics_view.clear()
        elif state.status == "loading":
            self._lyrics_view.clear_cover_art()
        if state.status == "error":
            now = time.monotonic()
            if now - self._last_error_skip >= 2.0:
                self._last_error_skip = now
                self._error_toast.popup()
                QTimer.singleShot(
                    800,
                    lambda: asyncio.ensure_future(self._ctrl.play_next()),
                )

    # ── navigation ────────────────────────────────────────────────────────────

    def _on_nav(self, page_id: str) -> None:
        self.sidebar.set_active_page(page_id)
        if page_id == "lyrics":
            self._toggle_lyrics()
            return
        if page_id in self._page_map:
            self.content.setCurrentIndex(self._page_map[page_id])
            self.now_playing.set_lyrics_active(False)

    def _show_lyrics(self) -> None:
        if self.content.currentIndex() == self._page_map["lyrics"]:
            return
        self._save_prev_page()
        self.content.setCurrentIndex(self._page_map["lyrics"])
        self.now_playing.set_lyrics_active(True)

    def _toggle_lyrics(self) -> None:
        if self.content.currentIndex() == self._page_map["lyrics"]:
            idx = self._page_map.get(self._prev_page, self._page_map["home"])
            self.content.setCurrentIndex(idx)
            self.now_playing.set_lyrics_active(False)
        else:
            self._save_prev_page()
            self.content.setCurrentIndex(self._page_map["lyrics"])
            self.now_playing.set_lyrics_active(True)

    def _save_prev_page(self) -> None:
        current_idx = self.content.currentIndex()
        self._prev_page = next(
            (k for k, v in self._page_map.items()
             if v == current_idx and k != "lyrics"),
            "home",
        )

    # ── queue panel ───────────────────────────────────────────────────────────

    def _show_queue(self) -> None:
        import time
        if self._queue_panel is None:
            self._queue_panel = QueuePanel(self._ctrl, self)
        # If the popup was just auto-closed because the user clicked this
        # button (Popup closes on press, clicked fires on release), skip
        # re-opening so the button acts as a proper toggle.
        if time.monotonic() - self._queue_panel.last_hide_time < 0.15:
            return
        self._queue_panel.refresh()
        btn = self.now_playing.queue_btn_global_rect()
        x = btn.right() - self._queue_panel.width()
        y = btn.top() - self._queue_panel.height() - 8
        self._queue_panel.move(x, y)
        self._queue_panel.show()

    # ── platform login ────────────────────────────────────────────────────────

    def _on_platform_login(self, platform_id: str) -> None:
        if platform_id == "netease":
            asyncio.ensure_future(self._ctrl.ensure_netease_auth(self))
        elif platform_id == "ytmusic":
            asyncio.ensure_future(self._ctrl.ensure_ytmusic_auth(self))
        elif platform_id == "spotify":
            asyncio.ensure_future(self._ctrl.ensure_spotify_auth(self))

    # ── styling ───────────────────────────────────────────────────────────────

    def _apply_styles(self) -> None:
        self.setStyleSheet(f"""
            QMainWindow, #appRoot {{
                background-color: #000000;
            }}
            QWidget {{
                font-family: "Inter", "SF Pro Display", sans-serif;
            }}
            #contentArea {{
                background-color: transparent;
                border-radius: 8px;
                border: none;
            }}
        """)
