from __future__ import annotations
import asyncio
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget,
)
from ui.theme import COLORS
from ui.components.sidebar import SidebarWidget
from ui.components.now_playing_bar import NowPlayingBar
from ui.pages.search_page import SearchPage


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
        self._page_map: dict[str, int] = {
            "search": self.content.addWidget(self._search_page),
        }

        body.addWidget(self.content, stretch=1)
        root.addLayout(body, stretch=1)

        self.now_playing = NowPlayingBar()
        root.addWidget(self.now_playing)

    def _wire_signals(self) -> None:
        ctrl = self._ctrl
        ctrl.state_changed.connect(self.now_playing.update_state)
        ctrl.position_changed.connect(self.now_playing.update_position)
        ctrl.netease_auth_changed.connect(
            lambda ok: self.sidebar.set_platform_status("netease", ok)
        )
        # ctrl.init() runs before MainWindow is constructed, so the signal fires
        # before the connection exists — sync the initial state explicitly here.
        self.sidebar.set_platform_status("netease", ctrl.is_netease_authenticated)
        self.now_playing.play_pause_clicked.connect(ctrl.toggle_play_pause)
        self.now_playing.seek_requested.connect(ctrl.seek)
        self.now_playing.next_clicked.connect(
            lambda: asyncio.ensure_future(ctrl.play_next())
        )
        self.now_playing.prev_clicked.connect(
            lambda: asyncio.ensure_future(ctrl.play_prev())
        )
        self.now_playing.volume_changed.connect(ctrl.set_volume)

    def _on_nav(self, page_id: str) -> None:
        self.sidebar.set_active_page(page_id)
        if page_id in self._page_map:
            self.content.setCurrentIndex(self._page_map[page_id])

    def _on_platform_login(self, platform_id: str) -> None:
        if platform_id == "netease":
            asyncio.ensure_future(self._ctrl.ensure_netease_auth(self))

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
