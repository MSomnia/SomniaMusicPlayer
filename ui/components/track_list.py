from __future__ import annotations
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QListWidget, QListWidgetItem, QLabel
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from core.models import Track
from ui.components.track_row import TrackRow, ROW_HEIGHT
from ui.theme import COLORS, FONTS, scrollbar_qss


class TrackListWidget(QWidget):
    track_selected  = pyqtSignal(object)  # Track — double-click to play
    queue_requested = pyqtSignal(object)  # Track — 加入队列 button

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._status_label = QLabel()
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setObjectName("statusLabel")
        self._status_label.hide()
        layout.addWidget(self._status_label)

        self._list = QListWidget()
        self._list.setObjectName("trackList")
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.viewport().setStyleSheet("background: transparent;")
        self._list.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self._list)

        self._apply_styles()

    def _on_double_click(self, item: QListWidgetItem) -> None:
        track: Track = item.data(Qt.ItemDataRole.UserRole)
        if track:
            self.track_selected.emit(track)

    def set_tracks(self, tracks: list[Track]) -> None:
        self._list.clear()
        self._status_label.hide()
        self._list.show()
        for track in tracks:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, track)
            item.setSizeHint(QSize(0, ROW_HEIGHT))
            self._list.addItem(item)
            row = TrackRow(track)
            row.queue_clicked.connect(self.queue_requested)
            self._list.setItemWidget(item, row)

    def clear(self) -> None:
        self._list.clear()
        self._status_label.hide()

    def show_loading(self) -> None:
        self._list.clear()
        self._list.hide()
        self._status_label.setText("搜索中…")
        self._status_label.show()

    def show_empty(self, msg: str = "无结果") -> None:
        self._list.clear()
        self._list.hide()
        self._status_label.setText(msg)
        self._status_label.show()

    def _apply_styles(self) -> None:
        c, f = COLORS, FONTS
        self.setStyleSheet(f"""
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
            #statusLabel {{
                color: {c['text_muted']};
                font-size: {f['size_sm']}px;
                padding: 32px;
            }}
            {scrollbar_qss()}
        """)
