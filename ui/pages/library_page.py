from __future__ import annotations
import asyncio
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QSplitter, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal
from core.models import Playlist
from ui.theme import COLORS, FONTS

_PLATFORMS = [
    ("netease", "网易云"),
    ("spotify", "Spotify"),
    ("ytmusic", "YouTube Music"),
]


class LibraryPage(QWidget):
    def __init__(self, ctrl, parent=None) -> None:
        super().__init__(parent)
        self._ctrl = ctrl
        self._current_platform = "netease"
        self._playlists: list[Playlist] = []
        self._setup_ui()
        ctrl.library_ready.connect(self._on_library_ready)

    # ── construction ──────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 0)
        layout.setSpacing(12)

        title = QLabel("我的库")
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

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("librarySplitter")

        # Left: playlist list
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        self._status_label = QLabel("点击平台 Tab 加载歌单")
        self._status_label.setObjectName("statusLabel")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(self._status_label)

        self._playlist_list = QListWidget()
        self._playlist_list.setObjectName("playlistList")
        self._playlist_list.hide()
        self._playlist_list.currentRowChanged.connect(self._on_playlist_selected)
        left_layout.addWidget(self._playlist_list, stretch=1)
        splitter.addWidget(left)

        # Right: track list + controls
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(12, 0, 0, 0)
        right_layout.setSpacing(8)

        self._playlist_name_label = QLabel("")
        self._playlist_name_label.setObjectName("sectionTitle")
        right_layout.addWidget(self._playlist_name_label)

        btn_row = QHBoxLayout()
        self._play_all_btn = QPushButton("▶ 全部播放")
        self._play_all_btn.setObjectName("playAllBtn")
        self._play_all_btn.clicked.connect(self._on_play_all)
        self._play_all_btn.hide()
        btn_row.addWidget(self._play_all_btn)
        btn_row.addStretch()
        right_layout.addLayout(btn_row)

        self._track_status_label = QLabel("")
        self._track_status_label.setObjectName("statusLabel")
        self._track_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_layout.addWidget(self._track_status_label)

        self._track_list = QListWidget()
        self._track_list.setObjectName("trackList")
        self._track_list.hide()
        self._track_list.itemDoubleClicked.connect(self._on_track_double_clicked)
        right_layout.addWidget(self._track_list, stretch=1)
        splitter.addWidget(right)

        splitter.setSizes([220, 600])
        layout.addWidget(splitter, stretch=1)

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
            }}
            #playlistList {{
                background-color: {c['bg_surface']};
                border: none;
                border-right: 1px solid {c['border']};
                color: {c['text_primary']};
                font-size: {f['size_sm']}px;
            }}
            #playlistList::item {{
                padding: 10px 12px;
                border-bottom: 1px solid {c['divider']};
            }}
            #playlistList::item:hover {{
                background-color: {c['bg_hover']};
            }}
            #playlistList::item:selected {{
                background-color: {c['bg_elevated']};
                border-left: 3px solid {c['accent']};
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
            #playAllBtn {{
                background-color: {c['accent']};
                border: none;
                border-radius: 6px;
                color: #000000;
                font-size: {f['size_sm']}px;
                font-weight: bold;
                padding: 6px 16px;
            }}
            #playAllBtn:hover {{
                background-color: {c['accent_dim']};
            }}
        """)

    # ── event handlers ────────────────────────────────────────────────────────

    def _on_tab(self, platform: str) -> None:
        if platform == self._current_platform:
            return
        self._current_platform = platform
        for pid, btn in self._tab_btns.items():
            btn.setChecked(pid == platform)
        self._clear_tracks()
        self._load_library(platform)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._load_library(self._current_platform)

    def _load_library(self, platform: str) -> None:
        self._playlist_list.hide()
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
        await self._ctrl.load_library(platform)

    def _on_library_ready(self, platform: str, playlists: list) -> None:
        if platform != self._current_platform:
            return
        self._playlists = playlists
        self._status_label.hide()
        self._playlist_list.clear()
        if not playlists:
            if platform == "ytmusic":
                self._status_label.setText(
                    "未找到歌单。\n"
                    "若已登录，可能是登录态已过期，请在侧边栏重新登录 YouTube Music。"
                )
            else:
                self._status_label.setText("暂无歌单")
            self._status_label.show()
            return
        for pl in playlists:
            count_str = f"  ({pl.track_count}首)" if pl.track_count else ""
            item = QListWidgetItem(f"{pl.name}{count_str}")
            item.setData(Qt.ItemDataRole.UserRole, pl)
            self._playlist_list.addItem(item)
        self._playlist_list.show()

    def _on_playlist_selected(self, row: int) -> None:
        if row < 0 or row >= len(self._playlists):
            return
        playlist = self._playlists[row]
        self._playlist_name_label.setText(playlist.name)
        self._track_list.hide()
        self._play_all_btn.hide()
        self._track_status_label.setText("加载歌曲中…")
        asyncio.ensure_future(self._load_playlist_tracks(playlist))

    async def _load_playlist_tracks(self, playlist) -> None:
        tracks = await self._ctrl.get_playlist_tracks(playlist)
        self._track_status_label.setText("")
        self._track_list.clear()
        if not tracks:
            self._track_status_label.setText("暂无歌曲")
            return
        for track in tracks:
            s = track.duration_ms // 1000
            text = f"{track.title}  —  {track.artist}  [{s // 60}:{s % 60:02d}]"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, track)
            self._track_list.addItem(item)
        self._track_list.show()
        self._play_all_btn.setProperty("_tracks", tracks)
        self._play_all_btn.show()

    def _on_track_double_clicked(self, item: QListWidgetItem) -> None:
        track = item.data(Qt.ItemDataRole.UserRole)
        if track:
            asyncio.ensure_future(self._ctrl.play_track(track))

    def _on_play_all(self) -> None:
        tracks = self._play_all_btn.property("_tracks")
        if tracks:
            self._ctrl.play_queue_tracks(tracks, 0)

    def _clear_tracks(self) -> None:
        self._track_list.clear()
        self._track_list.hide()
        self._play_all_btn.hide()
        self._playlist_name_label.setText("")
        self._track_status_label.setText("")
