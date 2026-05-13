from __future__ import annotations
import asyncio
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QListWidget, QListWidgetItem, QFrame, QSizePolicy,
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from ui.theme import COLORS, FONTS, scrollbar_qss
from ui.components.track_row import TrackRow, ROW_HEIGHT

_PLATFORMS = [
    ("netease", "网易云"),
    ("spotify", "Spotify"),
    ("ytmusic", "YouTube Music"),
]

_COLLAPSED_TRACK_COUNT = 5
_TRACK_ROW_HEIGHT = 38


class _HomeTrackList(QListWidget):
    def wheelEvent(self, event) -> None:  # type: ignore[override]
        event.ignore()


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
            btn.setProperty("platform", pid)
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
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._content_widget = QWidget()
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(16)
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
                background-color: transparent;
                border: 1px solid #FFFFFF;
                border-radius: 6px;
                color: #FFFFFF;
                font-size: {f['size_xs']}px;
                padding: 4px 12px;
            }}
            #platformTab:checked {{
                background-color: {c['accent']};
                border-color: {c['accent']};
                color: #000000;
                font-weight: bold;
            }}
            #platformTab[platform="spotify"]:checked {{
                background-color: {c['platform_spotify']};
                border-color: {c['platform_spotify']};
                color: #000000;
            }}
            #platformTab[platform="netease"]:checked {{
                background-color: {c['platform_netease']};
                border-color: {c['platform_netease']};
                color: #000000;
            }}
            #platformTab[platform="ytmusic"]:checked {{
                background-color: {c['platform_ytmusic']};
                border-color: {c['platform_ytmusic']};
                color: #FFFFFF;
            }}
            #platformTab:hover:!checked {{
                background-color: transparent;
                border-color: #FFFFFF;
                color: #FFFFFF;
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
            #sectionToggleBtn {{
                background-color: transparent;
                border: 1px solid {c['border']};
                border-radius: 6px;
                color: {c['text_secondary']};
                font-size: {f['size_xs']}px;
                padding: 5px 12px;
            }}
            #sectionToggleBtn:hover {{
                border-color: {c['text_secondary']};
                color: {c['text_primary']};
            }}
            #homeScroll {{
                background-color: {c['bg_base']};
            }}
            {scrollbar_qss()}
        """)

    # ── event handlers ────────────────────────────────────────────────────────

    def _on_tab(self, platform: str) -> None:
        same_platform = platform == self._current_platform
        self._current_platform = platform
        for pid, btn in self._tab_btns.items():
            btn.setChecked(pid == platform)
        if same_platform:
            return
        self._load_platform(platform)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._load_platform(self._current_platform)

    def _load_platform(self, platform: str) -> None:
        if self._ctrl.get_cached_home(platform) is None:
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
        expandable = len(sections) > 1
        for section_title, tracks in sections:
            self._add_section(section_title, tracks, expandable)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _clear_content(self) -> None:
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    @staticmethod
    def _fmt(ms: int) -> str:
        if not ms:
            return ""
        s = ms // 1000
        return f"[{s // 60}:{s % 60:02d}]"

    def _list_height(self, track_count: int) -> int:
        return max(1, track_count) * _TRACK_ROW_HEIGHT + 2

    def _set_section_expanded(
        self,
        list_widget: QListWidget,
        button: QPushButton,
        track_count: int,
        expanded: bool,
    ) -> None:
        shown_count = track_count if expanded else min(track_count, _COLLAPSED_TRACK_COUNT)
        list_widget.setFixedHeight(self._list_height(shown_count))
        button.setText("收起" if expanded else "展开")
        button.setProperty("expanded", expanded)

    def _add_section(self, title: str, tracks: list, expandable: bool) -> None:
        section = QWidget()
        section.setObjectName("homeSection")
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(0, 0, 0, 0)
        section_layout.setSpacing(0)

        sec_label = QLabel(title)
        sec_label.setObjectName("sectionTitle")
        section_layout.addWidget(sec_label)

        list_widget = _HomeTrackList() if expandable else QListWidget()
        list_widget.setObjectName("trackList")
        list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        if expandable:
            list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        list_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        if not expandable:
            list_widget.setMinimumHeight(140)
        for track in tracks:
            dur = self._fmt(track.duration_ms)
            text = f"{track.title}  —  {track.artist}" + (f"  {dur}" if dur else "")
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, track)
            item.setSizeHint(QSize(0, ROW_HEIGHT))
            list_widget.addItem(item)
            row = TrackRow(track, text)
            row.queue_clicked.connect(self._ctrl.add_to_queue)
            list_widget.setItemWidget(item, row)
        list_widget.itemDoubleClicked.connect(self._on_track_double_clicked)
        if not expandable:
            stretch = max(1, min(len(tracks), 10))
            section_layout.addWidget(list_widget, stretch=1)
            self._content_layout.addWidget(section, stretch=stretch)
            return

        toggle_btn = QPushButton()
        toggle_btn.setObjectName("sectionToggleBtn")
        toggle_btn.clicked.connect(
            lambda _checked=False, lw=list_widget, btn=toggle_btn, count=len(tracks):
                self._set_section_expanded(
                    lw,
                    btn,
                    count,
                    not bool(btn.property("expanded")),
                )
        )
        self._set_section_expanded(list_widget, toggle_btn, len(tracks), False)
        section_layout.addWidget(list_widget)
        section_layout.addWidget(toggle_btn)
        self._content_layout.addWidget(section)

    def _on_track_double_clicked(self, item: QListWidgetItem) -> None:
        track = item.data(Qt.ItemDataRole.UserRole)
        if not track:
            return
        list_widget = self.sender()
        if list_widget is None:
            asyncio.ensure_future(self._ctrl.play_track(track))
            return
        tracks = [
            list_widget.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(list_widget.count())
            if list_widget.item(i).data(Qt.ItemDataRole.UserRole) is not None
        ]
        try:
            start = tracks.index(track)
        except ValueError:
            start = 0
        self._ctrl.play_queue_tracks(tracks, start)
