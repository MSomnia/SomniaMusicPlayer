from __future__ import annotations
import asyncio
import time
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem,
)
from PyQt6.QtCore import Qt, QSize
from ui.components.track_row import fetch_cover, COVER_SIZE, COVER_RADIUS
from ui.theme import COLORS, FONTS, scrollbar_qss

_W = 380
_H_EMPTY = 110   # height when queue is empty
_H_FULL  = 440   # height when queue has tracks

# Column widths tuned for the 380 px panel
_ARTIST_W = 100
_DUR_W    = 48
_ROW_H    = 38


class _QueueRow(QWidget):
    """Single-row widget for the queue list: [cover] title | artist | duration."""

    def __init__(self, track, is_current: bool, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(_ROW_H)
        c, f = COLORS, FONTS

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(6)

        # ── Cover thumbnail ───────────────────────────────────────────────────
        self._cover_lbl = QLabel()
        self._cover_lbl.setFixedSize(COVER_SIZE, COVER_SIZE)
        self._cover_lbl.setObjectName("queueCover")
        layout.addWidget(self._cover_lbl)

        # ── Title ─────────────────────────────────────────────────────────────
        prefix = "▶  " if is_current else ""
        title_lbl = QLabel(prefix + track.title)
        title_lbl.setObjectName("queueColTitle")
        if is_current:
            title_lbl.setStyleSheet(
                f"color: {c['accent']}; font-weight: bold; background: transparent;"
            )
        layout.addWidget(title_lbl, stretch=1)

        # ── Artist ────────────────────────────────────────────────────────────
        artist_lbl = QLabel(track.artist)
        artist_lbl.setObjectName("queueColArtist")
        artist_lbl.setFixedWidth(_ARTIST_W)
        layout.addWidget(artist_lbl)

        # ── Duration ──────────────────────────────────────────────────────────
        s = track.duration_ms // 1000
        dur_lbl = QLabel(f"{s // 60}:{s % 60:02d}" if s else "")
        dur_lbl.setObjectName("queueColDuration")
        dur_lbl.setFixedWidth(_DUR_W)
        dur_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(dur_lbl)

        self.setStyleSheet(f"""
            _QueueRow {{ background: transparent; }}
            #queueCover {{
                background-color: {c['bg_elevated']};
                border-radius: {COVER_RADIUS}px;
            }}
            #queueColTitle {{
                color: {c['text_primary']};
                font-size: {f['size_sm']}px;
                background: transparent;
            }}
            #queueColArtist {{
                color: {c['text_secondary']};
                font-size: {f['size_xs']}px;
                background: transparent;
            }}
            #queueColDuration {{
                color: {c['text_muted']};
                font-size: {f['size_xs']}px;
                background: transparent;
            }}
        """)

        if track.album_cover_url:
            asyncio.ensure_future(self._load_cover(track.album_cover_url))

    async def _load_cover(self, url: str) -> None:
        pixmap = await fetch_cover(url, COVER_SIZE)
        if pixmap:
            try:
                self._cover_lbl.setPixmap(pixmap)
            except RuntimeError:
                pass


class QueuePanel(QWidget):
    """Popup panel showing the current play queue.

    Uses Qt.WindowType.Popup so Qt automatically closes it when the user
    clicks anywhere outside the panel.
    """

    def __init__(self, ctrl, parent=None) -> None:
        super().__init__(
            parent,
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint,
        )
        self._ctrl = ctrl
        self.last_hide_time: float = 0.0   # tracks when popup was last dismissed
        self.setFixedWidth(_W)
        self._setup_ui()
        self._apply_styles()
        ctrl.queue_changed.connect(self._on_queue_changed)

    # ── construction ──────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        self._title_label = QLabel("播放队列")
        self._title_label.setObjectName("panelTitle")
        header.addWidget(self._title_label)
        header.addStretch()

        clear_btn = QPushButton("清空")
        clear_btn.setObjectName("clearBtn")
        clear_btn.clicked.connect(self._on_clear)
        header.addWidget(clear_btn)
        layout.addLayout(header)

        self._status_label = QLabel("队列为空")
        self._status_label.setObjectName("statusLabel")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._status_label)

        self._list = QListWidget()
        self._list.setObjectName("queueList")
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.hide()
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self._list)

    def _apply_styles(self) -> None:
        c, f = COLORS, FONTS
        self.setStyleSheet(f"""
            QueuePanel {{
                background-color: {c['bg_surface']};
                border: 1px solid {c['border']};
                border-radius: 10px;
            }}
            #panelTitle {{
                color: {c['text_primary']};
                font-size: {f['size_md']}px;
                font-weight: bold;
            }}
            #statusLabel {{
                color: {c['text_muted']};
                font-size: {f['size_sm']}px;
                padding: 16px;
            }}
            #queueList {{
                background-color: {c['bg_surface']};
                border: none;
                border-radius: 0px;
                color: {c['text_primary']};
                font-size: {f['size_sm']}px;
            }}
            #queueList::item {{
                padding: 2px 4px;
                border-radius: 6px;
            }}
            #queueList::item:hover {{
                background-color: {c['bg_hover']};
                border-radius: 6px;
            }}
            #queueList::item:selected {{
                background-color: {c['bg_elevated']};
                border-radius: 6px;
            }}
            #clearBtn {{
                background: transparent;
                border: 1px solid {c['border']};
                border-radius: 4px;
                color: {c['text_secondary']};
                font-size: {f['size_xs']}px;
                padding: 4px 10px;
            }}
            #clearBtn:hover {{
                border-color: {c['text_secondary']};
                color: {c['text_primary']};
            }}
            {scrollbar_qss()}
        """)

    # ── public API ────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        self._on_queue_changed(self._ctrl.queue_tracks, self._ctrl.queue_index)

    # ── internal ──────────────────────────────────────────────────────────────

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self.last_hide_time = time.monotonic()

    def _on_queue_changed(self, tracks: list, current_index: int) -> None:
        self._list.clear()
        if not tracks:
            self._title_label.setText("播放队列")
            self._list.hide()
            self._status_label.show()
            self._status_label.setText("队列为空")
            self.setFixedHeight(_H_EMPTY)
            return
        remaining = max(0, len(tracks) - current_index - 1)
        self._title_label.setText(f"播放队列  ·  剩余 {remaining} 首")
        self._status_label.hide()
        self._list.show()
        self.setFixedHeight(_H_FULL)
        for i, track in enumerate(tracks):
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, i)
            item.setSizeHint(QSize(0, _ROW_H))
            self._list.addItem(item)
            self._list.setItemWidget(item, _QueueRow(track, i == current_index))
        if 0 <= current_index < self._list.count():
            self._list.scrollToItem(self._list.item(current_index))

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        index = item.data(Qt.ItemDataRole.UserRole)
        if index is not None:
            asyncio.ensure_future(self._ctrl.jump_to_queue_index(index))

    def _on_clear(self) -> None:
        self._ctrl._queue.clear()
        self._ctrl._emit_queue_changed()
