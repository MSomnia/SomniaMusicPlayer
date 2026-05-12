from __future__ import annotations
import asyncio
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton
from PyQt6.QtCore import QTimer
from ui.components.track_list import TrackListWidget
from ui.theme import COLORS, FONTS

_PLATFORMS = [
    ("netease", "网易云"),
    ("ytmusic", "YouTube Music"),
]


class SearchPage(QWidget):
    def __init__(self, ctrl, parent=None) -> None:
        super().__init__(parent)
        self._ctrl = ctrl
        self._current_platform = "netease"
        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(400)
        self._debounce.timeout.connect(self._on_timer_fired)
        self._setup_ui()
        ctrl.search_results_ready.connect(self._track_list.set_tracks)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 0)
        layout.setSpacing(12)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("搜索音乐…")
        self._search_input.setObjectName("searchInput")
        self._search_input.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._search_input)

        tab_row = QHBoxLayout()
        tab_row.setSpacing(8)
        self._tab_btns: dict[str, QPushButton] = {}
        for pid, label in _PLATFORMS:
            btn = QPushButton(label)
            btn.setObjectName("platformTab")
            btn.setCheckable(True)
            btn.setChecked(pid == self._current_platform)
            btn.clicked.connect(lambda _checked, p=pid: self._on_tab(p))
            self._tab_btns[pid] = btn
            tab_row.addWidget(btn)
        tab_row.addStretch()
        layout.addLayout(tab_row)

        self._track_list = TrackListWidget()
        self._track_list.track_selected.connect(
            lambda t: asyncio.ensure_future(self._ctrl.play_track(t))
        )
        layout.addWidget(self._track_list, stretch=1)

        self._apply_styles()

    def _apply_styles(self) -> None:
        c, f = COLORS, FONTS
        self.setStyleSheet(f"""
            #searchInput {{
                background-color: {c['bg_elevated']};
                border: 1px solid {c['border']};
                border-radius: 8px;
                color: {c['text_primary']};
                font-size: {f['size_sm']}px;
                padding: 8px 14px;
            }}
            #searchInput:focus {{
                border-color: {c['accent']};
            }}
            #platformTab {{
                background: transparent;
                border: 1px solid {c['border']};
                border-radius: 6px;
                color: {c['text_secondary']};
                font-size: {f['size_xs']}px;
                padding: 4px 12px;
            }}
            #platformTab:checked {{
                background-color: {c['accent']};
                border-color: {c['accent']};
                color: #000000;
                font-weight: bold;
            }}
            #platformTab:hover:!checked {{
                border-color: {c['text_secondary']};
                color: {c['text_primary']};
            }}
        """)

    def _on_tab(self, platform: str) -> None:
        if platform == self._current_platform:
            return
        self._current_platform = platform
        for pid, btn in self._tab_btns.items():
            btn.setChecked(pid == platform)
        self._track_list.clear()
        query = self._search_input.text().strip()
        if query:
            asyncio.ensure_future(self._do_search(query))

    def _on_text_changed(self, _text: str) -> None:
        self._debounce.start()

    def _on_timer_fired(self) -> None:
        asyncio.ensure_future(self._do_search(self._search_input.text()))

    async def _do_search(self, query: str) -> None:
        query = query.strip()
        if not query:
            self._track_list.clear()
            return

        platform = self._current_platform
        if platform == "netease":
            if not self._ctrl.is_netease_authenticated:
                ok = await self._ctrl.ensure_netease_auth(self)
                if not ok:
                    self._track_list.show_empty("需要登录网易云音乐")
                    return
        elif platform == "ytmusic":
            if not self._ctrl.is_ytmusic_authenticated:
                ok = await self._ctrl.ensure_ytmusic_auth(self)
                if not ok:
                    self._track_list.show_empty("需要登录 YouTube Music")
                    return

        self._track_list.show_loading()
        try:
            await self._ctrl.search(query, platform=platform)
        except Exception:
            self._track_list.show_empty("搜索失败，请检查网络连接")
