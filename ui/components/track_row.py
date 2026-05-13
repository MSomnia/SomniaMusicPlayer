from __future__ import annotations
import asyncio
import httpx
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt, QRectF, pyqtSignal
from PyQt6.QtGui import QPixmap, QPainter, QPainterPath
from core.models import Track
from ui.theme import COLORS, FONTS

ROW_HEIGHT    = 38
ARTIST_WIDTH  = 150
DUR_WIDTH     = 55
COVER_SIZE    = 28   # shared by TrackRow and _QueueRow
COVER_RADIUS  = 6    # corner radius applied to all cover pixmaps
_BTN_W        = 76
_BTN_H        = 24

# Module-level pixmap cache: URL → QPixmap (original resolution).
# Shared across all TrackRow / _QueueRow instances; avoids duplicate fetches.
_cover_cache: dict[str, QPixmap] = {}


def _apply_rounded(pixmap: QPixmap, radius: int) -> QPixmap:
    """Return a copy of *pixmap* with all four corners clipped to *radius*.

    Qt's CSS border-radius only rounds the widget background — it does not
    clip the pixmap itself.  We must paint through a QPainterPath mask so the
    image content is truly rounded.
    """
    out = QPixmap(pixmap.size())
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(out.rect()), radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, pixmap)
    painter.end()
    return out


async def fetch_cover(url: str, size: int) -> QPixmap | None:
    """Return a *size×size* rounded pixmap for *url*, using the module-level cache."""
    if not url:
        return None
    raw = _cover_cache.get(url)
    if raw is None:
        try:
            async with httpx.AsyncClient() as http:
                resp = await http.get(url, timeout=5.0)
                data = resp.content
            px = QPixmap()
            px.loadFromData(data)
            if px.isNull():
                return None
            _cover_cache[url] = px
            raw = px
        except Exception:
            return None
    scaled = raw.scaled(
        size, size,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    return _apply_rounded(scaled, COVER_RADIUS)


def _fmt_dur(ms: int) -> str:
    if not ms:
        return ""
    s = ms // 1000
    return f"{s // 60}:{s % 60:02d}"


class TrackRow(QWidget):
    """Three-column track row: [cover] title | artist | duration.

    A 'add to queue' button is absolutely positioned over the right end
    and revealed on hover — it does not affect the column layout.
    """

    queue_clicked = pyqtSignal(object)  # Track

    def __init__(self, track: Track, parent=None) -> None:
        super().__init__(parent)
        self._track = track
        self.setFixedHeight(ROW_HEIGHT)

        c, f = COLORS, FONTS

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(8)

        # ── Cover thumbnail ───────────────────────────────────────────────────
        self._cover_lbl = QLabel()
        self._cover_lbl.setFixedSize(COVER_SIZE, COVER_SIZE)
        self._cover_lbl.setObjectName("trackCover")
        layout.addWidget(self._cover_lbl)

        # ── Column 1: title (stretch) ─────────────────────────────────────────
        self._title_lbl = QLabel(track.title)
        self._title_lbl.setObjectName("colTitle")
        layout.addWidget(self._title_lbl, stretch=1)

        # ── Column 2: artist (fixed width) ───────────────────────────────────
        self._artist_lbl = QLabel(track.artist)
        self._artist_lbl.setObjectName("colArtist")
        self._artist_lbl.setFixedWidth(ARTIST_WIDTH)
        layout.addWidget(self._artist_lbl)

        # ── Column 3: duration (fixed width, right-aligned) ───────────────────
        self._dur_lbl = QLabel(_fmt_dur(track.duration_ms))
        self._dur_lbl.setObjectName("colDuration")
        self._dur_lbl.setFixedWidth(DUR_WIDTH)
        self._dur_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        layout.addWidget(self._dur_lbl)

        # ── Hover button (absolutely positioned, outside layout) ──────────────
        self._btn = QPushButton("加入队列", self)
        self._btn.setObjectName("addToQueueBtn")
        self._btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.hide()
        self._btn.clicked.connect(self._on_btn_clicked)

        self.setStyleSheet(f"""
            TrackRow {{ background-color: transparent; }}
            #trackCover {{
                background-color: {c['bg_elevated']};
                border-radius: {COVER_RADIUS}px;
            }}
            #colTitle {{
                color: {c['text_primary']};
                font-size: {f['size_sm']}px;
                background: transparent;
            }}
            #colArtist {{
                color: {c['text_secondary']};
                font-size: {f['size_sm']}px;
                background: transparent;
            }}
            #colDuration {{
                color: {c['text_muted']};
                font-size: {f['size_sm']}px;
                background: transparent;
            }}
            #addToQueueBtn {{
                background-color: {c['bg_elevated']};
                border: 1px solid {c['border']};
                border-radius: 4px;
                color: {c['text_secondary']};
                font-size: {f['size_xs']}px;
                padding: 3px 10px;
            }}
            #addToQueueBtn:hover {{
                color: {c['text_primary']};
                border-color: {c['text_secondary']};
            }}
        """)

        if track.album_cover_url:
            asyncio.ensure_future(self._load_cover(track.album_cover_url))

    # ── cover loading ─────────────────────────────────────────────────────────

    async def _load_cover(self, url: str) -> None:
        pixmap = await fetch_cover(url, COVER_SIZE)
        if pixmap:
            try:
                self._cover_lbl.setPixmap(pixmap)
            except RuntimeError:
                pass  # widget deleted before image arrived

    # ── button ────────────────────────────────────────────────────────────────

    def _on_btn_clicked(self) -> None:
        self.queue_clicked.emit(self._track)

    def _reposition_btn(self) -> None:
        x = self.width() - 8 - _BTN_W
        y = (ROW_HEIGHT - _BTN_H) // 2
        self._btn.setGeometry(x, y, _BTN_W, _BTN_H)

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        self._reposition_btn()
        self._btn.show()
        self._btn.raise_()

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self._btn.hide()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._btn.isVisible():
            self._reposition_btn()
