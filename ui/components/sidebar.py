from __future__ import annotations
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QCursor
from ui.frosted import paint_frosted_panel
from ui.theme import COLORS, FONTS


class _ClickableLabel(QLabel):
    clicked = pyqtSignal()

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class SidebarWidget(QWidget):
    nav_changed = pyqtSignal(str)               # "home"|"search"|"settings"
    platform_login_requested = pyqtSignal(str)  # "netease"|"spotify"|"ytmusic"
    standby_requested = pyqtSignal()            # emitted when title label is clicked

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setAutoFillBackground(False)
        self.setFixedWidth(200)
        self._nav_buttons: dict[str, QPushButton] = {}
        self._platform_buttons: dict[str, QPushButton] = {}
        self._platform_names: dict[str, str] = {}
        self._display_name = "Omnia"
        self._setup_ui()
        self._apply_styles()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(2)

        self._title = _ClickableLabel()
        self._title.setObjectName("appName")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title.clicked.connect(self.standby_requested)
        layout.addWidget(self._title)
        self._refresh_title()
        layout.addSpacing(16)

        for page_id, label in [
            ("search",  "🔍  搜索"),
            ("home",    "🏠  首页"),
        ]:
            layout.addWidget(self._make_nav_btn(page_id, label))

        layout.addWidget(self._make_divider())
        layout.addSpacing(4)

        section = QLabel("我的库")
        section.setObjectName("sectionLabel")
        layout.addWidget(section)

        for platform_id, name in [
            ("spotify",  "Spotify"),
            ("ytmusic",  "YouTube Music"),
            ("netease",  "网易云"),
        ]:
            layout.addWidget(self._make_platform_btn(platform_id, name))

        layout.addWidget(self._make_divider())
        layout.addStretch()

        layout.addWidget(self._make_nav_btn("settings", "⚙️  设置"))
        layout.addSpacing(8)

    def _make_nav_btn(self, page_id: str, label: str) -> QPushButton:
        btn = QPushButton(label)
        btn.setObjectName("navButton")
        btn.setCheckable(True)
        btn.clicked.connect(lambda _checked, p=page_id: self.nav_changed.emit(p))
        self._nav_buttons[page_id] = btn
        return btn

    def _make_platform_btn(self, platform_id: str, name: str) -> QPushButton:
        btn = QPushButton(f"○  {name}")
        btn.setObjectName("platformButton")
        btn.setProperty("platform", platform_id)
        btn.setCheckable(True)
        btn.clicked.connect(
            lambda: self.platform_login_requested.emit(platform_id)
        )
        self._platform_buttons[platform_id] = btn
        self._platform_names[platform_id] = name
        return btn

    def _make_divider(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName("divider")
        return line

    def _apply_styles(self) -> None:
        c, f = COLORS, FONTS
        self.setStyleSheet(f"""
            #sidebar {{
                background-color: transparent;
                border: none;
                border-radius: 8px;
            }}
            #appName {{
                color: {c['text_primary']};
                font-size: {f['size_md']}px;
                font-weight: bold;
                padding: 0 12px;
            }}
            #navButton {{
                text-align: left;
                padding: 8px 14px;
                margin: 1px 10px;
                background: transparent;
                border: none;
                border-left: 3px solid transparent;
                color: {c['text_secondary']};
                font-size: {f['size_sm']}px;
                border-radius: 8px;
            }}
            #navButton:hover {{
                background-color: {c['bg_hover']};
                color: {c['text_primary']};
                border-left-color: {c['accent']};
            }}
            #navButton:checked {{
                background-color: {c['bg_hover']};
                color: {c['text_primary']};
                border-left-color: {c['accent']};
            }}
            #platformButton {{
                text-align: left;
                padding: 8px 14px;
                margin: 1px 10px;
                background: transparent;
                border: none;
                border-left: 3px solid transparent;
                color: {c['text_secondary']};
                font-size: {f['size_sm']}px;
                border-radius: 8px;
            }}
            #platformButton:hover {{
                background-color: {c['bg_hover']};
            }}
            #platformButton:checked {{
                background-color: {c['bg_hover']};
            }}
            #platformButton[platform="spotify"] {{
                color: {c['platform_spotify']};
            }}
            #platformButton[platform="spotify"]:checked {{
                border-left-color: {c['platform_spotify']};
            }}
            #platformButton[platform="netease"] {{
                color: {c['platform_netease']};
            }}
            #platformButton[platform="netease"]:checked {{
                border-left-color: {c['platform_netease']};
            }}
            #platformButton[platform="ytmusic"] {{
                color: {c['platform_ytmusic']};
            }}
            #platformButton[platform="ytmusic"]:checked {{
                border-left-color: {c['platform_ytmusic']};
            }}
            #divider {{
                color: {c['divider']};
                margin: 4px 12px;
                max-height: 1px;
            }}
            #sectionLabel {{
                color: {c['text_muted']};
                font-size: {f['size_xs']}px;
                padding: 4px 16px;
            }}
        """)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        paint_frosted_panel(self, painter)
        super().paintEvent(event)

    def set_active_page(self, page_id: str) -> None:
        for pid, btn in self._nav_buttons.items():
            btn.setChecked(pid == page_id)
        if page_id in self._nav_buttons:
            self.set_active_platform(None)

    def set_active_platform(self, platform_id: str | None) -> None:
        for pid, btn in self._platform_buttons.items():
            btn.setChecked(pid == platform_id)

    def set_platform_status(self, platform_id: str, logged_in: bool) -> None:
        btn = self._platform_buttons.get(platform_id)
        if not btn:
            return
        name = self._platform_names[platform_id]
        if logged_in:
            btn.setText(f"●  {name}")
        else:
            btn.setText(f"○  {name}")

    def set_display_name(self, name: str) -> None:
        self._display_name = name.strip() or "Omnia"
        self._refresh_title()

    def _refresh_title(self) -> None:
        hour = datetime.now().hour
        if 5 <= hour < 12:
            greeting = "早安"
        elif 12 <= hour < 18:
            greeting = "午安"
        else:
            greeting = "晚安"
        self._title.setText(f"{greeting}，{self._display_name}")
