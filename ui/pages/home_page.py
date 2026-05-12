from __future__ import annotations
import asyncio
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QListWidget, QListWidgetItem, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal
from ui.theme import COLORS, FONTS

_PLATFORMS = [
    ("netease", "网易云"),
    ("spotify", "Spotify"),
    ("ytmusic", "YouTube Music"),
]


class HomePage(QWidget):
    def __init__(self, ctrl, parent=None) -> None:
        super().__init__(parent)
        self._ctrl = ctrl
        self._current_platform = "netease"
        self._sections: list[tuple[str, list]] = []
        self._setup_ui()
        ctrl.home_sections_ready.connect(self._on_sections_ready)

    # ── construction ──────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 0)
        layout.setSpacing(12)

        title = QLabel("首页")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

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

        self._status_label = QLabel("点击平台 Tab 加载推荐")
        self._status_label.setObjectName("statusLabel")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._status_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setObjectName("homeScroll")
        self._content_widget = QWidget()
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(16)
        self._content_layout.addStretch()
        scroll.setWidget(self._content_widget)
        layout.addWidget(scroll, stretch=1)

        self._apply_styles()

    def _apply_styles(self) -> None:
        c, f = COLORS, FONTS
        self.setStyleSheet(f"""
            #pageTitle {{
                color: {c['text_primary']};
                font-size: {f['size_xl']}px;
                font-weight: bold;
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
            #statusLabel {{
                color: {c['text_muted']};
                font-size: {f['size_sm']}px;
                padding: 32px;
            }}
            #sectionTitle {{
                color: {c['text_primary']};
                font-size: {f['size_md']}px;
                font-weight: bold;
                padding: 4px 0;
            }}
            #trackList {{
                background-color: {c['bg_base']};
                border: none;
                color: {c['text_primary']};
                font-size: {f['size_sm']}px;
            }}
            #trackList::item {{
                padding: 8px 12px;
                border-bottom: 1px solid {c['divider']};
            }}
            #trackList::item:hover {{
                background-color: {c['bg_hover']};
            }}
            #trackList::item:selected {{
                background-color: {c['bg_elevated']};
            }}
            #homeScroll {{
                background-color: {c['bg_base']};
            }}
        """)

    # ── event handlers ────────────────────────────────────────────────────────

    def _on_tab(self, platform: str) -> None:
        if platform == self._current_platform:
            return
        self._current_platform = platform
        for pid, btn in self._tab_btns.items():
            btn.setChecked(pid == platform)
        self._load_platform(platform)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._load_platform(self._current_platform)

    def _load_platform(self, platform: str) -> None:
        self._clear_content()
        self._status_label.setText("加载中…")
        self._status_label.show()
        asyncio.ensure_future(self._do_load(platform))

    async def _do_load(self, platform: str) -> None:
        if platform == "netease" and not self._ctrl.is_netease_authenticated:
            ok = await self._ctrl.ensure_netease_auth(self)
            if not ok:
                self._status_label.setText("需要登录网易云音乐")
                return
        elif platform == "ytmusic" and not self._ctrl.is_ytmusic_authenticated:
            ok = await self._ctrl.ensure_ytmusic_auth(self)
            if not ok:
                self._status_label.setText("需要登录 YouTube Music")
                return
        elif platform == "spotify" and not self._ctrl.is_spotify_authenticated:
            ok = await self._ctrl.ensure_spotify_auth(self)
            if not ok:
                self._status_label.setText("需要登录 Spotify")
                return
        await self._ctrl.load_home(platform)

    def _on_sections_ready(self, platform: str, sections: list) -> None:
        if platform != self._current_platform:
            return
        self._status_label.hide()
        self._clear_content()
        if not sections:
            self._status_label.setText("暂无推荐内容")
            self._status_label.show()
            return
        for section_title, tracks in sections:
            self._add_section(section_title, tracks)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _clear_content(self) -> None:
        while self._content_layout.count() > 1:
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    @staticmethod
    def _fmt(ms: int) -> str:
        s = ms // 1000
        return f"{s // 60}:{s % 60:02d}"

    def _add_section(self, title: str, tracks: list) -> None:
        sec_label = QLabel(title)
        sec_label.setObjectName("sectionTitle")
        self._content_layout.insertWidget(self._content_layout.count() - 1, sec_label)

        list_widget = QListWidget()
        list_widget.setObjectName("trackList")
        list_widget.setMaximumHeight(min(len(tracks), 10) * 38)
        for track in tracks:
            text = f"{track.title}  —  {track.artist}  [{self._fmt(track.duration_ms)}]"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, track)
            list_widget.addItem(item)
        list_widget.itemDoubleClicked.connect(self._on_track_double_clicked)
        self._content_layout.insertWidget(self._content_layout.count() - 1, list_widget)

    def _on_track_double_clicked(self, item: QListWidgetItem) -> None:
        track = item.data(Qt.ItemDataRole.UserRole)
        if track:
            asyncio.ensure_future(self._ctrl.play_track(track))
