from __future__ import annotations
import asyncio
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QListWidgetItem, QSplitter,
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from ui.components.track_row import TrackRow, ROW_HEIGHT
from core.models import Playlist
from ui.theme import COLORS, FONTS, scrollbar_qss

_PLATFORMS = [
    ("netease", "网易云音乐"),
    ("spotify", "Spotify"),
    ("ytmusic", "YouTube Music"),
]

_PLATFORM_LABELS = dict(_PLATFORMS)


class LibraryPage(QWidget):
    artist_clicked = pyqtSignal(object)   # Track
    status_message = pyqtSignal(str, bool)  # message, success

    def __init__(self, ctrl, parent=None) -> None:
        super().__init__(parent)
        self._ctrl = ctrl
        self._current_platform: str | None = None
        self._loading_platform: str | None = None
        self._playlists: list[Playlist] = []
        self._current_playlist: Playlist | None = None
        self._setup_ui()
        ctrl.library_ready.connect(self._on_library_ready)

    # ── construction ──────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 0)
        layout.setSpacing(12)

        self._title = QLabel("我的库")
        self._title.setObjectName("pageTitle")
        layout.addWidget(self._title)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("librarySplitter")

        # Left: playlist list
        left = QWidget()
        left.setObjectName("libraryPane")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        self._status_label = QLabel("从侧边栏的平台账号打开音乐库")
        self._status_label.setObjectName("statusLabel")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(self._status_label)

        self._playlist_list = QListWidget()
        self._playlist_list.setObjectName("playlistList")
        self._playlist_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._playlist_list.viewport().setStyleSheet("background: transparent;")
        self._playlist_list.hide()
        self._playlist_list.currentRowChanged.connect(self._on_playlist_selected)
        left_layout.addWidget(self._playlist_list, stretch=1)
        splitter.addWidget(left)

        # Right: track list + controls
        right = QWidget()
        right.setObjectName("libraryPane")
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
        self._track_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._track_list.viewport().setStyleSheet("background: transparent;")
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
            #pageTitle[platform="spotify"] {{
                color: {c['platform_spotify']};
            }}
            #pageTitle[platform="netease"] {{
                color: {c['platform_netease']};
            }}
            #pageTitle[platform="ytmusic"] {{
                color: {c['platform_ytmusic']};
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
            #librarySplitter,
            #libraryPane {{
                background-color: transparent;
            }}
            #playlistList {{
                background-color: transparent;
                border: none;
                border-right: 1px solid {c['border']};
                color: {c['text_primary']};
                font-size: {f['size_sm']}px;
            }}
            #playlistList::item {{
                padding: 10px 12px;
                border-radius: 8px;
            }}
            #playlistList::item:hover {{
                background-color: {c['bg_hover']};
                border-radius: 8px;
            }}
            #playlistList::item:selected {{
                background-color: {c['bg_elevated']};
                border-left: 3px solid {c['accent']};
                border-radius: 8px;
            }}
            #playlistList[platform="spotify"]::item:selected {{
                border-left-color: {c['platform_spotify']};
            }}
            #playlistList[platform="netease"]::item:selected {{
                border-left-color: {c['platform_netease']};
            }}
            #playlistList[platform="ytmusic"]::item:selected {{
                border-left-color: {c['platform_ytmusic']};
            }}
            #trackList {{
                background-color: transparent;
                border: none;
                color: {c['text_primary']};
                font-size: {f['size_sm']}px;
            }}
            #trackList::item {{
                padding: 2px 4px;
                border-radius: 8px;
            }}
            #trackList::item:hover {{
                background-color: {c['bg_hover']};
                border-radius: 8px;
            }}
            #trackList::item:selected {{
                background-color: {c['bg_elevated']};
                border-radius: 8px;
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
            #playAllBtn[platform="spotify"],
            #playAllBtn[platform="spotify"]:hover {{
                background-color: {c['platform_spotify']};
            }}
            #playAllBtn[platform="netease"],
            #playAllBtn[platform="netease"]:hover {{
                background-color: {c['platform_netease']};
            }}
            #playAllBtn[platform="ytmusic"],
            #playAllBtn[platform="ytmusic"]:hover {{
                background-color: {c['platform_ytmusic']};
                color: #FFFFFF;
            }}
            {scrollbar_qss()}
        """)

    # ── event handlers ────────────────────────────────────────────────────────

    def set_platform(self, platform: str) -> None:
        if platform not in _PLATFORM_LABELS:
            return
        same_platform = platform == self._current_platform
        self._current_platform = platform
        self._title.setText(_PLATFORM_LABELS[platform])
        self._title.setProperty("platform", platform)
        self._playlist_list.setProperty("platform", platform)
        self._play_all_btn.setProperty("platform", platform)
        for widget in (self._title, self._playlist_list, self._play_all_btn):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        if not same_platform:
            self._playlists = []
            self._playlist_list.clear()
            self._playlist_list.hide()
            self._playlist_name_label.setText("")
            self._clear_tracks()
        if same_platform and self._ctrl.get_cached_library(platform) is not None:
            return
        self._load_library(platform)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._current_platform:
            self._load_library(self._current_platform)

    def _load_library(self, platform: str) -> None:
        if self._loading_platform == platform:
            return
        if self._ctrl.get_cached_library(platform) is None:
            self._playlist_list.hide()
            self._status_label.setText("加载中…")
            self._status_label.show()
        self._loading_platform = platform
        asyncio.ensure_future(self._do_load(platform))

    async def _do_load(self, platform: str) -> None:
        try:
            if platform == "netease" and not self._ctrl.is_netease_authenticated:
                self._status_label.setText("需要登录网易云音乐")
                return
            elif platform == "ytmusic" and not self._ctrl.is_ytmusic_authenticated:
                self._status_label.setText("需要登录 YouTube Music")
                return
            elif platform == "spotify" and not self._ctrl.is_spotify_authenticated:
                self._status_label.setText("需要登录 Spotify")
                return
            await self._ctrl.load_library(platform)
        finally:
            if self._loading_platform == platform:
                self._loading_platform = None

    def _on_library_ready(self, platform: str, playlists: list) -> None:
        if platform != self._current_platform:
            return
        # Skip re-render when background refresh returns identical playlist IDs
        if playlists and self._playlists and \
                [p.id for p in playlists] == [p.id for p in self._playlists]:
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
        self._current_playlist = playlist
        self._playlist_name_label.setText(playlist.name)
        cached = self._ctrl.get_cached_tracks(playlist.platform, playlist.id)
        if cached is not None:
            self._display_tracks(cached)
        else:
            self._track_list.hide()
            self._play_all_btn.hide()
            self._track_status_label.setText("加载歌曲中…")
        asyncio.ensure_future(self._load_playlist_tracks(playlist))

    def _display_tracks(self, tracks: list) -> None:
        self._track_status_label.setText("")
        self._track_list.clear()
        if not tracks:
            self._track_status_label.setText("暂无歌曲")
            return
        playlist = self._current_playlist
        for track in tracks:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, track)
            item.setSizeHint(QSize(0, ROW_HEIGHT))
            self._track_list.addItem(item)
            row = TrackRow(track)
            row.queue_clicked.connect(self._ctrl.add_to_queue)
            row.artist_clicked.connect(self.artist_clicked)
            if playlist is not None:
                row.set_removable(True)
                row.remove_clicked.connect(
                    lambda t, pl=playlist: asyncio.ensure_future(
                        self._on_remove_track(t, pl)
                    )
                )
            self._track_list.setItemWidget(item, row)
        self._track_list.show()
        self._play_all_btn.setProperty("_tracks", tracks)
        self._play_all_btn.show()

    async def _load_playlist_tracks(self, playlist) -> None:
        tracks = await self._ctrl.get_playlist_tracks(playlist)
        if self._current_playlist and self._current_playlist.id == playlist.id:
            self._display_tracks(tracks)

    async def _on_remove_track(self, track, playlist) -> None:
        ok = await self._ctrl.remove_track_from_playlist(track, playlist)
        if ok:
            self._remove_track_from_view(track)
            self.status_message.emit(f"已从「{playlist.name}」移出", True)
        else:
            self.status_message.emit("移出歌单失败", False)

    def _remove_track_from_view(self, track) -> None:
        for i in range(self._track_list.count()):
            item = self._track_list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) is track:
                self._track_list.takeItem(i)
                break

    def _on_track_double_clicked(self, item: QListWidgetItem) -> None:
        track = item.data(Qt.ItemDataRole.UserRole)
        if not track:
            return
        tracks = [
            self._track_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self._track_list.count())
            if self._track_list.item(i).data(Qt.ItemDataRole.UserRole) is not None
        ]
        try:
            start = tracks.index(track)
        except ValueError:
            start = 0
        self._ctrl.play_queue_tracks(tracks, start)

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
