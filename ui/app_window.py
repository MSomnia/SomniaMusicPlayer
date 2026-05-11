from __future__ import annotations
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget,
)
from ui.theme import COLORS
from ui.components.sidebar import SidebarWidget
from ui.components.now_playing_bar import NowPlayingBar


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SomniaMusicPlayer")
        self.setMinimumSize(900, 600)
        self._setup_ui()
        self._apply_styles()
        self.sidebar.set_active_page("home")

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Body: sidebar + main content area
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self.sidebar = SidebarWidget()
        self.sidebar.nav_changed.connect(self._on_nav)
        body.addWidget(self.sidebar)

        self.content = QStackedWidget()
        self.content.setObjectName("contentArea")
        body.addWidget(self.content, stretch=1)

        root.addLayout(body, stretch=1)

        # Persistent bottom playback bar
        self.now_playing = NowPlayingBar()
        root.addWidget(self.now_playing)

    def _on_nav(self, page_id: str) -> None:
        self.sidebar.set_active_page(page_id)

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
