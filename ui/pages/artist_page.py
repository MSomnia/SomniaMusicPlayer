from __future__ import annotations
import asyncio
import httpx
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem,
)
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QPixmap, QPainter, QPainterPath, QCursor
from ui.theme import COLORS, FONTS, scrollbar_qss
from ui.components.track_row import TrackRow, ROW_HEIGHT
from core.models import Artist, Track

_PLATFORM_NAMES = {
    "netease": "网易云音乐",
    "spotify": "Spotify",
    "ytmusic": "YouTube Music",
}


class ArtistPage(QWidget):
    back_requested = pyqtSignal()
    play_track = pyqtSignal(object)       # Track
    queue_track = pyqtSignal(object)      # Track
    artist_clicked = pyqtSignal(object)   # Track

    def __init__(self, ctrl, parent=None) -> None:
        super().__init__(parent)
        self._ctrl = ctrl
        self._artist: Artist | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 0)
        layout.setSpacing(12)

        # ── Header ────────────────────────────────────────────────────────────
        header = QHBoxLayout()
        header.setSpacing(16)

        back_btn = QPushButton("← 返回")
        back_btn.setObjectName("backBtn")
        back_btn.setFixedWidth(80)
        back_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        back_btn.clicked.connect(self.back_requested)
        header.addWidget(back_btn)

        self._cover_lbl = QLabel()
        self._cover_lbl.setFixedSize(80, 80)
        self._cover_lbl.setObjectName("artistCover")
        self._cover_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(self._cover_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(4)
        self._name_lbl = QLabel("—")
        self._name_lbl.setObjectName("pageTitle")
        title_col.addWidget(self._name_lbl)
        self._platform_lbl = QLabel("")
        self._platform_lbl.setObjectName("artistPlatform")
        title_col.addWidget(self._platform_lbl)
        title_col.addStretch()
        header.addLayout(title_col, stretch=1)

        layout.addLayout(header)

        # ── Section label ─────────────────────────────────────────────────────
        section_lbl = QLabel("热门歌曲")
        section_lbl.setObjectName("sectionLabel")
        layout.addWidget(section_lbl)

        # ── Track list ────────────────────────────────────────────────────────
        self._list = QListWidget()
        self._list.setObjectName("artistTrackList")
        self._list.setFrameShape(QListWidget.Shape.NoFrame)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        c = COLORS
        self._list.setStyleSheet(scrollbar_qss() + f"""
            QListWidget {{ background: transparent; border: none; outline: none; }}
            QListWidget::item {{ padding: 2px 4px; border-radius: 8px; }}
            QListWidget::item:hover {{ background-color: {c['bg_hover']}; border-radius: 8px; }}
            QListWidget::item:selected {{ background-color: {c['bg_elevated']}; border-radius: 8px; }}
        """)
        layout.addWidget(self._list, stretch=1)

        self._apply_styles()

    def _apply_styles(self) -> None:
        c, f = COLORS, FONTS
        self.setStyleSheet(f"""
            #backBtn {{
                background: transparent;
                color: {c['text_secondary']};
                font-size: {f['size_sm']}px;
                border: none;
                text-align: left;
                padding: 0;
            }}
            #backBtn:hover {{ color: {c['text_primary']}; }}
            #artistCover {{
                background-color: {c['bg_elevated']};
                border-radius: 40px;
            }}
            #pageTitle {{
                color: {c['text_primary']};
                font-size: {f['size_lg']}px;
                font-weight: bold;
            }}
            #artistPlatform {{
                color: {c['text_secondary']};
                font-size: {f['size_sm']}px;
            }}
            #sectionLabel {{
                color: {c['text_primary']};
                font-size: {f['size_md']}px;
                font-weight: bold;
            }}
        """)

    # ── public API ────────────────────────────────────────────────────────────

    def load_artist(self, artist: Artist) -> None:
        self._artist = artist
        self._name_lbl.setText(artist.name)
        self._platform_lbl.setText(_PLATFORM_NAMES.get(artist.platform, artist.platform))
        self._cover_lbl.setText("")
        self._cover_lbl.setPixmap(QPixmap())
        self._list.clear()
        if artist.image_url:
            asyncio.ensure_future(self._load_cover(artist.image_url))

    def load_tracks(self, tracks: list[Track]) -> None:
        self._list.clear()
        for track in tracks:
            row = TrackRow(track)
            row.queue_clicked.connect(self.queue_track)
            row.artist_clicked.connect(self.artist_clicked)
            item = QListWidgetItem(self._list)
            item.setSizeHint(QSize(0, ROW_HEIGHT))
            item.setData(Qt.ItemDataRole.UserRole, track)
            self._list.setItemWidget(item, row)

    # ── internal ──────────────────────────────────────────────────────────────

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        track = item.data(Qt.ItemDataRole.UserRole)
        if track:
            self.play_track.emit(track)

    async def _load_cover(self, url: str) -> None:
        try:
            async with httpx.AsyncClient() as http:
                resp = await http.get(url, timeout=8.0)
                data = resp.content
            px = QPixmap()
            px.loadFromData(data)
            if px.isNull():
                return
            dpr = QApplication.primaryScreen().devicePixelRatio()
            phys = int(80 * dpr)
            px = px.scaled(
                phys, phys,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            # Circular clip
            out = QPixmap(phys, phys)
            out.fill(Qt.GlobalColor.transparent)
            painter = QPainter(out)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            path = QPainterPath()
            path.addEllipse(0.0, 0.0, float(phys), float(phys))
            painter.setClipPath(path)
            painter.drawPixmap(0, 0, px)
            painter.end()
            out.setDevicePixelRatio(dpr)
            self._cover_lbl.setPixmap(out)
        except Exception:
            pass
