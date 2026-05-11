from __future__ import annotations
import asyncio
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLineEdit
from PyQt6.QtCore import QTimer
from ui.components.track_list import TrackListWidget
from ui.theme import COLORS, FONTS


class SearchPage(QWidget):
    def __init__(self, ctrl, parent=None) -> None:
        super().__init__(parent)
        self._ctrl = ctrl
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
        self._search_input.setPlaceholderText("搜索网易云音乐…")
        self._search_input.setObjectName("searchInput")
        self._search_input.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._search_input)

        self._track_list = TrackListWidget()
        self._track_list.track_selected.connect(
            lambda t: asyncio.ensure_future(self._ctrl.play_track(t))
        )
        layout.addWidget(self._track_list, stretch=1)

        self._apply_styles()

    def _on_text_changed(self, text: str) -> None:
        self._debounce.start()

    def _on_timer_fired(self) -> None:
        asyncio.ensure_future(self._do_search(self._search_input.text()))

    async def _do_search(self, query: str) -> None:
        query = query.strip()
        if not query:
            return
        if not self._ctrl.is_netease_authenticated:
            ok = await self._ctrl.ensure_netease_auth(self)
            if not ok:
                return
        self._track_list.show_loading()
        await self._ctrl.search(query)

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
        """)
