from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal
from ui.theme import COLORS, FONTS


class SidebarWidget(QWidget):
    nav_changed = pyqtSignal(str)  # "home" | "search" | "library" | "settings"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedWidth(200)
        self._nav_buttons: dict[str, QPushButton] = {}
        self._setup_ui()
        self._apply_styles()

    # ── construction ──────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(2)

        title = QLabel("Somnia")
        title.setObjectName("appName")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addSpacing(16)

        for page_id, label in [
            ("search",  "🔍  搜索"),
            ("home",    "🏠  首页"),
            ("library", "📚  我的库"),
        ]:
            layout.addWidget(self._make_nav_btn(page_id, label))

        layout.addWidget(self._make_divider())
        layout.addSpacing(4)

        section = QLabel("平台账号")
        section.setObjectName("sectionLabel")
        layout.addWidget(section)

        for _pid, name in [
            ("spotify", "Spotify"),
            ("ytmusic", "YouTube Music"),
            ("netease", "网易云"),
        ]:
            layout.addWidget(self._make_platform_row(name))

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

    def _make_divider(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName("divider")
        return line

    def _make_platform_row(self, name: str) -> QWidget:
        row = QWidget()
        row.setObjectName("platformRow")
        vl = QVBoxLayout(row)
        vl.setContentsMargins(16, 4, 16, 4)
        lbl = QLabel(f"○  {name}")
        lbl.setObjectName("platformLabel")
        vl.addWidget(lbl)
        return row

    def _apply_styles(self) -> None:
        c, f = COLORS, FONTS
        self.setStyleSheet(f"""
            SidebarWidget {{
                background-color: {c['bg_surface']};
                border-right: 1px solid {c['border']};
            }}
            #appName {{
                color: {c['text_primary']};
                font-size: {f['size_md']}px;
                font-weight: bold;
                padding: 0 12px;
            }}
            #navButton {{
                text-align: left;
                padding: 8px 16px;
                background: transparent;
                border: none;
                border-left: 3px solid transparent;
                color: {c['text_secondary']};
                font-size: {f['size_sm']}px;
                border-radius: 0;
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
            #platformLabel {{
                color: {c['text_secondary']};
                font-size: {f['size_sm']}px;
            }}
        """)

    # ── public API ────────────────────────────────────────────────────────────

    def set_active_page(self, page_id: str) -> None:
        for pid, btn in self._nav_buttons.items():
            btn.setChecked(pid == page_id)
