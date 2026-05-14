from __future__ import annotations
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QApplication,
)
from PyQt6.QtCore import Qt, QPoint, QRectF, pyqtSignal
from PyQt6.QtGui import QCursor, QPainter, QPainterPath, QColor
from core.models import Playlist
from ui.theme import COLORS, FONTS

_PLATFORM_LABELS = {
    "netease": "网易云音乐",
    "spotify": "Spotify",
    "ytmusic": "YouTube Music",
}

_WIDTH = 220
_MAX_LIST_HEIGHT = 260
_RADIUS = 6


class PlaylistPickerPopup(QFrame):
    playlist_selected = pyqtSignal(object)  # Playlist

    def __init__(self, platform: str, parent=None) -> None:
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(_WIDTH)

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 6, 4, 6)
        root.setSpacing(0)

        # Title
        title_lbl = QLabel(
            f"加入到 {_PLATFORM_LABELS.get(platform, platform)} 歌单"
        )
        title_lbl.setObjectName("title_lbl")
        title_lbl.setStyleSheet(f"""
            color: {COLORS['text_muted']};
            font-size: {FONTS['size_sm']}px;
            padding: 4px 8px;
        """)
        root.addWidget(title_lbl)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {COLORS['border']}; margin: 2px 0;")
        root.addWidget(sep)

        # Loading label (default visible)
        self._loading_lbl = QLabel("加载歌单中...")
        self._loading_lbl.setObjectName("loading_lbl")
        self._loading_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._loading_lbl.setStyleSheet(f"""
            color: {COLORS['text_muted']};
            font-size: {FONTS['size_sm']}px;
            padding: 12px 8px;
        """)
        root.addWidget(self._loading_lbl)

        # Scroll area (hidden until data arrives)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._scroll.setMaximumHeight(_MAX_LIST_HEIGHT)
        self._scroll.setVisible(False)
        self._scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._scroll.viewport().setAutoFillBackground(False)

        self._list_widget = QWidget()
        self._list_widget.setAutoFillBackground(False)
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(1)
        self._scroll.setWidget(self._list_widget)
        root.addWidget(self._scroll)

    # ── public API ───────────────────────────────────────────────────────────

    def show_at(self, pos: QPoint) -> None:
        self.adjustSize()
        screen = QApplication.primaryScreen().availableGeometry()
        x = min(pos.x(), screen.right() - _WIDTH - 4)
        y = min(pos.y(), screen.bottom() - self.sizeHint().height() - 4)
        self.move(max(x, screen.left()), max(y, screen.top()))
        self.show()

    def set_playlists(self, playlists: list[Playlist]) -> None:
        if not self.isVisible():
            return
        self._loading_lbl.setVisible(False)
        self._clear_list()

        if not playlists:
            lbl = QLabel("没有可加入的歌单")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"""
                color: {COLORS['text_muted']};
                font-size: {FONTS['size_sm']}px;
                padding: 12px 8px;
            """)
            self._list_layout.addWidget(lbl)
        else:
            for playlist in playlists:
                name = playlist.name or "未命名歌单"
                count = f"  {playlist.track_count}首" if playlist.track_count else ""
                btn = QPushButton(f"{name}{count}")
                btn.setFlat(True)
                btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                btn.setStyleSheet(f"""
                    QPushButton {{
                        text-align: left;
                        padding: 6px 12px;
                        border: none;
                        border-radius: 4px;
                        color: {COLORS['text_primary']};
                        font-size: {FONTS['size_sm']}px;
                        background: transparent;
                    }}
                    QPushButton:hover {{
                        background-color: {COLORS['bg_hover']};
                    }}
                """)
                btn.clicked.connect(
                    lambda checked, p=playlist: self._on_item_clicked(p)
                )
                self._list_layout.addWidget(btn)

        self._scroll.setVisible(True)
        self.adjustSize()

    def set_error(self, msg: str) -> None:
        if not self.isVisible():
            return
        self._loading_lbl.setText(msg)

    # ── internal ─────────────────────────────────────────────────────────────

    def _clear_list(self) -> None:
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _on_item_clicked(self, playlist: Playlist) -> None:
        self.playlist_selected.emit(playlist)
        self.close()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(
            QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5),
            _RADIUS, _RADIUS,
        )
        painter.fillPath(path, QColor(COLORS['bg_elevated']))
        painter.setPen(QColor(COLORS['border']))
        painter.drawPath(path)

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)
