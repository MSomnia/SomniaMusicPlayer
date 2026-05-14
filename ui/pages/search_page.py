from __future__ import annotations
import asyncio
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QLabel, QScrollArea, QFrame, QApplication,
)
from PyQt6.QtCore import Qt, QTimer, QSize, pyqtSignal
from PyQt6.QtGui import QPixmap, QCursor
import httpx
from ui.components.track_list import TrackListWidget
from ui.theme import COLORS, FONTS

_PLATFORMS = [
    ("netease", "网易云"),
    ("spotify", "Spotify"),
    ("ytmusic", "YouTube Music"),
]

_COVER_SIZE = 96   # album card cover px


class _AlbumCard(QWidget):
    """Clickable album card: cover image + name + artist."""

    clicked = pyqtSignal(object)   # Album

    def __init__(self, album, parent=None) -> None:
        super().__init__(parent)
        self._album = album
        self.setFixedSize(110, 148)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        c, f = COLORS, FONTS
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._cover_lbl = QLabel()
        self._cover_lbl.setFixedSize(_COVER_SIZE, _COVER_SIZE)
        self._cover_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cover_lbl.setObjectName("albumCardCover")
        layout.addWidget(self._cover_lbl)

        name_lbl = QLabel(album.name)
        name_lbl.setObjectName("albumCardName")
        name_lbl.setWordWrap(True)
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        name_lbl.setMaximumWidth(110)
        layout.addWidget(name_lbl)

        artist_lbl = QLabel(album.artist)
        artist_lbl.setObjectName("albumCardArtist")
        artist_lbl.setMaximumWidth(110)
        layout.addWidget(artist_lbl)

        self.setStyleSheet(f"""
            _AlbumCard {{ background: transparent; }}
            #albumCardCover {{
                background-color: {c['bg_elevated']};
                border-radius: 6px;
            }}
            #albumCardName {{
                color: {c['text_primary']};
                font-size: {f['size_xs']}px;
                font-weight: bold;
            }}
            #albumCardArtist {{
                color: {c['text_secondary']};
                font-size: {f['size_xs']}px;
            }}
        """)

    def set_cover(self, pixmap: QPixmap) -> None:
        dpr = QApplication.primaryScreen().devicePixelRatio()
        phys = int(_COVER_SIZE * dpr)
        scaled = pixmap.scaled(
            phys, phys,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        scaled.setDevicePixelRatio(dpr)
        self._cover_lbl.setPixmap(scaled)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._album)
        super().mousePressEvent(event)


class SearchPage(QWidget):
    artist_clicked = pyqtSignal(object)  # Track
    playlist_requested = pyqtSignal(object)  # Track

    def __init__(self, ctrl, parent=None) -> None:
        super().__init__(parent)
        self._ctrl = ctrl
        self._current_platform = "netease"
        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(400)
        self._debounce.timeout.connect(self._on_timer_fired)
        self._album_cards: list[_AlbumCard] = []
        self._cover_tasks: list[asyncio.Task] = []
        self._current_album_tracks: list = []
        self._setup_ui()
        ctrl.search_results_ready.connect(self._on_tracks_ready)
        ctrl.album_search_ready.connect(self._on_albums_ready)

    # ── construction ──────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 0)
        layout.setSpacing(12)

        # ── Search controls (visible in search mode) ──────────────────────────
        self._search_controls = QWidget()
        self._search_controls.setObjectName("searchControls")
        sc_layout = QVBoxLayout(self._search_controls)
        sc_layout.setContentsMargins(0, 0, 0, 0)
        sc_layout.setSpacing(8)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("搜索音乐…")
        self._search_input.setObjectName("searchInput")
        self._search_input.setProperty("platform", self._current_platform)
        self._search_input.textChanged.connect(self._on_text_changed)
        sc_layout.addWidget(self._search_input)

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
        sc_layout.addLayout(tab_row)

        # Album shelf (horizontal scroll)
        self._album_shelf = QWidget()
        self._album_shelf.setObjectName("albumShelf")
        self._album_shelf.hide()
        shelf_outer = QVBoxLayout(self._album_shelf)
        shelf_outer.setContentsMargins(0, 4, 0, 0)
        shelf_outer.setSpacing(4)

        shelf_title = QLabel("专辑")
        shelf_title.setObjectName("shelfTitle")
        shelf_outer.addWidget(shelf_title)

        self._scroll_area = QScrollArea()
        self._scroll_area.setObjectName("albumScroll")
        self._scroll_area.setFixedHeight(_COVER_SIZE + 60)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.viewport().setStyleSheet("background: transparent;")

        self._cards_widget = QWidget()
        self._cards_widget.setObjectName("albumCards")
        self._cards_layout = QHBoxLayout(self._cards_widget)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(12)
        self._cards_layout.addStretch()
        self._scroll_area.setWidget(self._cards_widget)
        shelf_outer.addWidget(self._scroll_area)

        sc_layout.addWidget(self._album_shelf)
        layout.addWidget(self._search_controls)

        # ── Album view header (visible in album mode) ─────────────────────────
        self._album_header = QWidget()
        self._album_header.setObjectName("albumHeader")
        self._album_header.hide()
        ah_layout = QHBoxLayout(self._album_header)
        ah_layout.setContentsMargins(0, 0, 0, 0)
        ah_layout.setSpacing(12)

        self._back_btn = QPushButton("← 返回")
        self._back_btn.setObjectName("backBtn")
        self._back_btn.clicked.connect(self._on_back)
        ah_layout.addWidget(self._back_btn)

        self._album_cover_lbl = QLabel()
        self._album_cover_lbl.setFixedSize(60, 60)
        self._album_cover_lbl.setObjectName("albumHeaderCover")
        ah_layout.addWidget(self._album_cover_lbl)

        info_col = QVBoxLayout()
        info_col.setSpacing(2)
        self._album_name_lbl = QLabel()
        self._album_name_lbl.setObjectName("albumHeaderName")
        self._album_artist_lbl = QLabel()
        self._album_artist_lbl.setObjectName("albumHeaderArtist")
        info_col.addWidget(self._album_name_lbl)
        info_col.addWidget(self._album_artist_lbl)
        info_col.addStretch()
        ah_layout.addLayout(info_col, stretch=1)

        self._play_all_btn = QPushButton("▶ 全部播放")
        self._play_all_btn.setObjectName("albumPlayAllBtn")
        self._play_all_btn.setEnabled(False)
        self._play_all_btn.clicked.connect(self._on_play_all)
        ah_layout.addWidget(self._play_all_btn)

        layout.addWidget(self._album_header)

        # ── Track list (always present, content switches per mode) ────────────
        self._track_list = TrackListWidget()
        self._track_list.track_selected.connect(self._on_track_selected)
        self._track_list.queue_requested.connect(self._ctrl.add_to_queue)
        self._track_list.playlist_requested.connect(self.playlist_requested)
        self._track_list.artist_clicked.connect(self.artist_clicked)
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
            #searchInput:focus {{ border-color: {c['accent']}; }}
            #searchInput[platform="spotify"]:focus {{ border-color: {c['platform_spotify']}; }}
            #searchInput[platform="netease"]:focus  {{ border-color: {c['platform_netease']}; }}
            #searchInput[platform="ytmusic"]:focus  {{ border-color: {c['platform_ytmusic']}; }}
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
                color: #000;
                font-weight: bold;
            }}
            #platformTab[platform="spotify"]:checked {{
                background-color: {c['platform_spotify']};
                border-color: {c['platform_spotify']};
                color: #000;
            }}
            #platformTab[platform="netease"]:checked {{
                background-color: {c['platform_netease']};
                border-color: {c['platform_netease']};
                color: #000;
            }}
            #platformTab[platform="ytmusic"]:checked {{
                background-color: {c['platform_ytmusic']};
                border-color: {c['platform_ytmusic']};
                color: #fff;
            }}
            #platformTab:unchecked:hover {{
                background-color: {c['bg_hover']};
                border-color: {c['text_secondary']};
                color: {c['text_primary']};
            }}
            #platformTab[platform="spotify"]:unchecked:hover {{
                background-color: rgba(30, 215, 96, 32);
                border-color: {c['platform_spotify']};
                color: {c['platform_spotify']};
            }}
            #platformTab[platform="netease"]:unchecked:hover {{
                background-color: rgba(250, 87, 31, 32);
                border-color: {c['platform_netease']};
                color: {c['platform_netease']};
            }}
            #platformTab[platform="ytmusic"]:unchecked:hover {{
                background-color: rgba(255, 0, 0, 32);
                border-color: {c['platform_ytmusic']};
                color: {c['platform_ytmusic']};
            }}
            #shelfTitle {{
                color: {c['text_secondary']};
                font-size: {f['size_xs']}px;
                font-weight: bold;
                letter-spacing: 1px;
                text-transform: uppercase;
            }}
            #searchControls,
            #albumShelf,
            #albumScroll,
            #albumCards,
            #albumHeader {{
                background: transparent;
            }}
            #backBtn {{
                background: transparent;
                border: 1px solid {c['border']};
                border-radius: 6px;
                color: {c['text_secondary']};
                font-size: {f['size_xs']}px;
                padding: 6px 14px;
            }}
            #backBtn:hover {{ color: {c['text_primary']}; border-color: {c['text_secondary']}; }}
            #albumHeaderCover {{
                background-color: {c['bg_elevated']};
                border-radius: 6px;
            }}
            #albumHeaderName {{
                color: {c['text_primary']};
                font-size: {f['size_md']}px;
                font-weight: bold;
            }}
            #albumHeaderArtist {{
                color: {c['text_secondary']};
                font-size: {f['size_sm']}px;
            }}
            #albumPlayAllBtn {{
                background-color: {c['accent']};
                border: none;
                border-radius: 6px;
                color: #000;
                font-size: {f['size_sm']}px;
                font-weight: bold;
                padding: 7px 18px;
            }}
            #albumPlayAllBtn:hover {{ background-color: {c['accent_dim']}; }}
            #albumPlayAllBtn:disabled {{
                background-color: {c['bg_elevated']};
                color: {c['text_muted']};
            }}
        """)

    # ── event handlers ────────────────────────────────────────────────────────

    def _on_tab(self, platform: str) -> None:
        same = platform == self._current_platform
        self._current_platform = platform
        for pid, btn in self._tab_btns.items():
            btn.setChecked(pid == platform)
        if same:
            return
        self._search_input.setProperty("platform", platform)
        self._search_input.style().unpolish(self._search_input)
        self._search_input.style().polish(self._search_input)
        self._track_list.clear()
        self._clear_album_shelf()
        query = self._search_input.text().strip()
        if query:
            asyncio.ensure_future(self._do_search(query))

    def _on_text_changed(self, _text: str) -> None:
        self._debounce.start()

    def _on_timer_fired(self) -> None:
        asyncio.ensure_future(self._do_search(self._search_input.text()))

    def _on_track_selected(self, track) -> None:
        asyncio.ensure_future(self._ctrl.play_track(track))

    def _on_back(self) -> None:
        self._album_header.hide()
        self._search_controls.show()
        # Restore previous track results (re-search with current text)
        query = self._search_input.text().strip()
        if query:
            self._track_list.show_loading()
            asyncio.ensure_future(self._ctrl.search(query, platform=self._current_platform))
        else:
            self._track_list.clear()

    def _on_album_card_clicked(self, album) -> None:
        self._search_controls.hide()
        self._album_header.show()
        self._album_name_lbl.setText(album.name)
        self._album_artist_lbl.setText(album.artist)
        self._album_cover_lbl.clear()
        self._current_album_tracks = []
        self._play_all_btn.setEnabled(False)
        self._track_list.show_loading()
        asyncio.ensure_future(self._load_album(album))
        if album.cover_url:
            asyncio.ensure_future(self._set_header_cover(album.cover_url))

    # ── search flow ───────────────────────────────────────────────────────────

    async def _do_search(self, query: str) -> None:
        query = query.strip()
        if not query:
            self._track_list.clear()
            self._clear_album_shelf()
            return
        platform = self._current_platform
        if not await self._ensure_auth(platform):
            return
        self._track_list.show_loading()
        self._clear_album_shelf()
        # Tracks and albums fetched concurrently
        asyncio.ensure_future(self._ctrl.search(query, platform=platform))
        asyncio.ensure_future(self._ctrl.search_albums(query, platform=platform))

    async def _ensure_auth(self, platform: str) -> bool:
        if platform == "netease" and not self._ctrl.is_netease_authenticated:
            ok = await self._ctrl.ensure_netease_auth(self)
            if not ok:
                self._track_list.show_empty("需要登录网易云音乐")
                return False
        elif platform == "ytmusic" and not self._ctrl.is_ytmusic_authenticated:
            ok = await self._ctrl.ensure_ytmusic_auth(self)
            if not ok:
                self._track_list.show_empty("需要登录 YouTube Music")
                return False
        elif platform == "spotify" and not self._ctrl.is_spotify_authenticated:
            ok = await self._ctrl.ensure_spotify_auth(self)
            if not ok:
                self._track_list.show_empty("需要登录 Spotify")
                return False
        return True

    # ── signal handlers ───────────────────────────────────────────────────────

    def _on_tracks_ready(self, tracks: list) -> None:
        self._track_list.set_tracks(tracks)

    def _on_albums_ready(self, platform: str, albums: list) -> None:
        if platform != self._current_platform:
            return
        self._clear_album_shelf()
        if not albums:
            return
        # Insert cards before the stretch
        for album in albums:
            card = _AlbumCard(album)
            card.clicked.connect(self._on_album_card_clicked)
            # Insert before the trailing stretch item
            self._cards_layout.insertWidget(self._cards_layout.count() - 1, card)
            self._album_cards.append(card)
            if album.cover_url:
                task = asyncio.ensure_future(self._load_card_cover(card, album.cover_url))
                self._cover_tasks.append(task)
        self._album_shelf.show()

    # ── album detail ──────────────────────────────────────────────────────────

    async def _load_album(self, album) -> None:
        tracks = await self._ctrl.get_album_tracks(album)
        if not tracks:
            self._track_list.show_empty("专辑内暂无歌曲")
        else:
            self._current_album_tracks = tracks
            self._play_all_btn.setEnabled(True)
            self._track_list.set_tracks(tracks)

    def _on_play_all(self) -> None:
        if self._current_album_tracks:
            self._ctrl.play_queue_tracks(self._current_album_tracks, 0)

    async def _set_header_cover(self, url: str) -> None:
        pixmap = await _fetch_pixmap(url)
        if pixmap and not pixmap.isNull():
            dpr = QApplication.primaryScreen().devicePixelRatio()
            phys = int(60 * dpr)
            scaled = pixmap.scaled(phys, phys,
                                   Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                   Qt.TransformationMode.SmoothTransformation)
            scaled.setDevicePixelRatio(dpr)
            self._album_cover_lbl.setPixmap(scaled)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _clear_album_shelf(self) -> None:
        # Cancel in-flight cover fetches before deleting widgets
        for task in self._cover_tasks:
            task.cancel()
        self._cover_tasks.clear()
        for card in self._album_cards:
            self._cards_layout.removeWidget(card)
            card.deleteLater()
        self._album_cards.clear()
        self._album_shelf.hide()

    @staticmethod
    async def _load_card_cover(card: _AlbumCard, url: str) -> None:
        pixmap = await _fetch_pixmap(url)
        if pixmap and not pixmap.isNull():
            try:
                card.set_cover(pixmap)
            except RuntimeError:
                pass  # widget deleted before cover arrived (new search started)


async def _fetch_pixmap(url: str) -> QPixmap | None:
    try:
        async with httpx.AsyncClient() as http:
            resp = await http.get(url, timeout=6.0)
            data = resp.content
        px = QPixmap()
        px.loadFromData(data)
        return px
    except Exception:
        return None
