from __future__ import annotations
import asyncio
import time
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem,
)
from PyQt6.QtCore import Qt
from ui.theme import COLORS, FONTS, scrollbar_qss

_W = 380
_H_EMPTY = 110   # height when queue is empty
_H_FULL  = 440   # height when queue has tracks


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
                padding: 8px 12px;
                border-bottom: 1px solid {c['divider']};
            }}
            #queueList::item:hover {{
                background-color: {c['bg_hover']};
            }}
            #queueList::item:selected {{
                background-color: {c['bg_elevated']};
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
            s = track.duration_ms // 1000
            dur = f"  [{s // 60}:{s % 60:02d}]" if s else ""
            text = f"{track.title}  —  {track.artist}{dur}"
            if i == current_index:
                text = f"▶  {text}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, i)
            if i == current_index:
                font = item.font()
                font.setBold(True)
                item.setFont(font)
                item.setForeground(
                    __import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(COLORS["accent"])
                )
            self._list.addItem(item)
        if 0 <= current_index < self._list.count():
            self._list.scrollToItem(self._list.item(current_index))

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        index = item.data(Qt.ItemDataRole.UserRole)
        if index is not None:
            asyncio.ensure_future(self._ctrl.jump_to_queue_index(index))

    def _on_clear(self) -> None:
        self._ctrl._queue.clear()
        self._ctrl._emit_queue_changed()
