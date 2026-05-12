from __future__ import annotations
import asyncio
import ctypes
import ctypes.util
import logging
import sys
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget,
)
from ui.theme import COLORS
from ui.components.sidebar import SidebarWidget
from ui.components.now_playing_bar import NowPlayingBar
from ui.components.lyrics_view import LyricsView
from ui.pages.search_page import SearchPage

logger = logging.getLogger(__name__)


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
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self.sidebar = SidebarWidget()
        self.sidebar.nav_changed.connect(self._on_nav)
        self.sidebar.platform_login_requested.connect(self._on_platform_login)
        body.addWidget(self.sidebar)

        self.content = QStackedWidget()
        self.content.setObjectName("contentArea")

        self._search_page = SearchPage(self._ctrl)
        self._lyrics_view = LyricsView()
        self._page_map: dict[str, int] = {
            "search": self.content.addWidget(self._search_page),
            "lyrics": self.content.addWidget(self._lyrics_view),
        }
        self._prev_page: str = "search"

        body.addWidget(self.content, stretch=1)
        root.addLayout(body, stretch=1)

        self.now_playing = NowPlayingBar()
        root.addWidget(self.now_playing)

    def _wire_signals(self) -> None:
        ctrl = self._ctrl
        ctrl.state_changed.connect(self.now_playing.update_state)
        ctrl.state_changed.connect(self._on_state_changed)
        ctrl.position_changed.connect(self.now_playing.update_position)
        ctrl.position_changed.connect(self._lyrics_view.update_position)
        ctrl.netease_auth_changed.connect(
            lambda ok: self.sidebar.set_platform_status("netease", ok)
        )
        ctrl.ytmusic_auth_changed.connect(
            lambda ok: self.sidebar.set_platform_status("ytmusic", ok)
        )
        ctrl.lyrics_ready.connect(self._lyrics_view.set_lyrics)
        ctrl.cover_color_ready.connect(self._lyrics_view.set_cover_color)
        ctrl.cover_art_bytes.connect(self.now_playing.set_cover_pixmap_from_bytes)
        # ctrl.init() runs before MainWindow is constructed, so the signal fires
        # before the connection exists — sync the initial state explicitly here.
        self.sidebar.set_platform_status("netease", ctrl.is_netease_authenticated)
        self.sidebar.set_platform_status("ytmusic", ctrl.is_ytmusic_authenticated)
        self.now_playing.play_pause_clicked.connect(ctrl.toggle_play_pause)
        self.now_playing.seek_requested.connect(ctrl.seek)
        self.now_playing.next_clicked.connect(
            lambda: asyncio.ensure_future(ctrl.play_next())
        )
        self.now_playing.prev_clicked.connect(
            lambda: asyncio.ensure_future(ctrl.play_prev())
        )
        self.now_playing.volume_changed.connect(ctrl.set_volume)
        self.now_playing.lyrics_toggled.connect(self._toggle_lyrics)
        self.now_playing.track_info_clicked.connect(self._show_lyrics)
        self._lyrics_view.back_requested.connect(self._toggle_lyrics)

    def _on_state_changed(self, state) -> None:
        if state.current_track is None:
            self._lyrics_view.clear()

    def _show_lyrics(self) -> None:
        """Always navigate to the lyrics page (used by track-info click)."""
        if self.content.currentIndex() == self._page_map["lyrics"]:
            return
        self._prev_page = next(
            (k for k, v in self._page_map.items()
             if v == self.content.currentIndex() and k != "lyrics"),
            "search",
        )
        self.content.setCurrentIndex(self._page_map["lyrics"])
        self.now_playing.set_lyrics_active(True)

    def _toggle_lyrics(self) -> None:
        if self.content.currentIndex() == self._page_map["lyrics"]:
            idx = self._page_map.get(self._prev_page, self._page_map["search"])
            self.content.setCurrentIndex(idx)
            self.now_playing.set_lyrics_active(False)
        else:
            self._prev_page = next(
                (k for k, v in self._page_map.items()
                 if v == self.content.currentIndex() and k != "lyrics"),
                "search",
            )
            self.content.setCurrentIndex(self._page_map["lyrics"])
            self.now_playing.set_lyrics_active(True)

    def _on_nav(self, page_id: str) -> None:
        self.sidebar.set_active_page(page_id)
        if page_id in self._page_map:
            self.content.setCurrentIndex(self._page_map[page_id])

    def _on_platform_login(self, platform_id: str) -> None:
        if platform_id == "netease":
            asyncio.ensure_future(self._ctrl.ensure_netease_auth(self))
        elif platform_id == "ytmusic":
            asyncio.ensure_future(self._ctrl.ensure_ytmusic_auth(self))

    def _apply_styles(self) -> None:
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background-color: {COLORS['bg_base']};
                font-family: "Inter", "SF Pro Display", sans-serif;
            }}
            #contentArea {{
                background-color: {COLORS['bg_base']};
            }}
        """)
