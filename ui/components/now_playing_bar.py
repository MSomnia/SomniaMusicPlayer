from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QSlider,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QPainter, QPainterPath, QCursor
from ui.theme import COLORS, FONTS
from core.models import PlayerState


class _ClickableLabel(QLabel):
    """QLabel that emits clicked() on left mouse press."""
    clicked = pyqtSignal()

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class NowPlayingBar(QWidget):
    play_pause_clicked = pyqtSignal()
    next_clicked = pyqtSignal()
    prev_clicked = pyqtSignal()
    seek_requested = pyqtSignal(int)   # ms
    volume_changed = pyqtSignal(int)   # 0–100
    shuffle_toggled = pyqtSignal()
    repeat_toggled = pyqtSignal()
    lyrics_toggled = pyqtSignal()
    queue_requested = pyqtSignal()
    track_info_clicked = pyqtSignal()  # cover or title clicked

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(90)
        self._duration_ms: int = 0
        self._setup_ui()
        self._apply_styles()

    # ── construction ──────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 0, 16, 0)
        root.setSpacing(0)
        root.addWidget(self._build_left(), stretch=0)
        root.addWidget(self._build_center(), stretch=1)
        root.addWidget(self._build_right(), stretch=0)

    def _build_left(self) -> QWidget:
        widget = QWidget()
        widget.setMinimumWidth(200)
        hl = QHBoxLayout(widget)
        hl.setSpacing(12)
        hl.setContentsMargins(0, 0, 0, 0)

        self._cover = _ClickableLabel()
        self._cover.setFixedSize(48, 48)
        self._cover.setObjectName("coverThumb")
        self._cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cover.clicked.connect(self.track_info_clicked)
        hl.addWidget(self._cover)

        info = QVBoxLayout()
        info.setSpacing(2)
        self._title = _ClickableLabel("—")
        self._title.setObjectName("trackTitle")
        self._title.clicked.connect(self.track_info_clicked)
        self._artist = QLabel("—")
        self._artist.setObjectName("trackArtist")
        info.addWidget(self._title)
        info.addWidget(self._artist)
        hl.addLayout(info)
        hl.addStretch()
        return widget

    def _build_center(self) -> QWidget:
        widget = QWidget()
        vl = QVBoxLayout(widget)
        vl.setContentsMargins(0, 8, 0, 8)
        vl.setSpacing(6)

        # Playback controls
        btn_row = QHBoxLayout()
        btn_row.setSpacing(16)
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._shuffle_btn = self._ctrl("⇌")
        self._shuffle_btn.setCheckable(True)
        self._shuffle_btn.clicked.connect(self.shuffle_toggled)
        btn_row.addWidget(self._shuffle_btn)

        self._prev_btn = self._ctrl("⏮")
        self._prev_btn.clicked.connect(self.prev_clicked)
        btn_row.addWidget(self._prev_btn)

        self._play_btn = QPushButton("▶")
        self._play_btn.setObjectName("playBtn")
        self._play_btn.setFixedSize(36, 36)
        self._play_btn.clicked.connect(self.play_pause_clicked)
        btn_row.addWidget(self._play_btn)

        self._next_btn = self._ctrl("⏭")
        self._next_btn.clicked.connect(self.next_clicked)
        btn_row.addWidget(self._next_btn)

        self._repeat_btn = self._ctrl("↻")
        self._repeat_btn.setCheckable(True)
        self._repeat_btn.clicked.connect(self.repeat_toggled)
        btn_row.addWidget(self._repeat_btn)

        vl.addLayout(btn_row)

        # Progress bar
        prog_row = QHBoxLayout()
        prog_row.setSpacing(8)

        self._pos_label = QLabel("0:00")
        self._pos_label.setObjectName("timeLabel")
        prog_row.addWidget(self._pos_label)

        self._progress = QSlider(Qt.Orientation.Horizontal)
        self._progress.setObjectName("progressSlider")
        self._progress.setRange(0, 10_000)
        # sliderMoved: live seek while dragging
        self._progress.sliderMoved.connect(self._on_seek)
        # sliderReleased: covers both drag-end and click-on-track
        self._progress.sliderReleased.connect(
            lambda: self._on_seek(self._progress.value())
        )
        prog_row.addWidget(self._progress, stretch=1)

        self._dur_label = QLabel("0:00")
        self._dur_label.setObjectName("timeLabel")
        prog_row.addWidget(self._dur_label)

        vl.addLayout(prog_row)
        return widget

    def _build_right(self) -> QWidget:
        widget = QWidget()
        widget.setMinimumWidth(150)
        hl = QHBoxLayout(widget)
        hl.setContentsMargins(8, 0, 0, 0)
        hl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        hl.setSpacing(8)

        self._queue_btn = self._ctrl("☰")
        self._queue_btn.setObjectName("controlBtn")
        self._queue_btn.setToolTip("播放队列")
        self._queue_btn.clicked.connect(self.queue_requested)
        hl.addWidget(self._queue_btn)

        self._lyrics_btn = self._ctrl("♫")
        self._lyrics_btn.setObjectName("lyricsBtn")
        self._lyrics_btn.setCheckable(True)
        self._lyrics_btn.setToolTip("歌词")
        self._lyrics_btn.clicked.connect(self.lyrics_toggled)
        hl.addWidget(self._lyrics_btn)

        hl.addWidget(QLabel("🔊"))

        self._volume = QSlider(Qt.Orientation.Horizontal)
        self._volume.setObjectName("volumeSlider")
        self._volume.setRange(0, 100)
        self._volume.setValue(70)
        self._volume.setFixedWidth(100)
        self._volume.valueChanged.connect(self.volume_changed)
        hl.addWidget(self._volume)
        return widget

    def _ctrl(self, icon: str) -> QPushButton:
        btn = QPushButton(icon)
        btn.setObjectName("controlBtn")
        return btn

    def _apply_styles(self) -> None:
        c, f = COLORS, FONTS
        self.setStyleSheet(f"""
            NowPlayingBar {{
                background-color: {c['bg_surface']};
                border-top: 1px solid {c['border']};
            }}
            #coverThumb {{
                background-color: {c['bg_elevated']};
                border-radius: 6px;
                border: 2px solid transparent;
            }}
            #coverThumb:hover {{
                border: 2px solid {c['accent']};
            }}
            #trackTitle {{
                color: {c['text_primary']};
                font-size: {f['size_sm']}px;
                font-weight: bold;
            }}
            #trackTitle:hover {{
                color: {c['accent']};
                text-decoration: underline;
            }}
            #trackArtist {{
                color: {c['text_secondary']};
                font-size: {f['size_xs']}px;
            }}
            #controlBtn {{
                background: transparent;
                border: none;
                color: {c['text_secondary']};
                font-size: 15px;
                padding: 4px 8px;
            }}
            #controlBtn:hover {{ color: {c['text_primary']}; }}
            #controlBtn:checked {{ color: {c['accent']}; }}
            #lyricsBtn:checked {{ color: {c['accent']}; }}
            #playBtn {{
                background-color: {c['accent']};
                border: none;
                color: #000000;
                font-size: 15px;
                border-radius: 18px;
            }}
            #playBtn:hover {{ background-color: {c['accent_dim']}; }}
            QSlider::groove:horizontal {{
                height: 4px;
                background: {c['bg_elevated']};
                border-radius: 2px;
            }}
            QSlider::sub-page:horizontal {{
                background: {c['accent']};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                width: 0; height: 0;
            }}
            QSlider::handle:horizontal:hover {{
                width: 12px; height: 12px;
                margin: -4px 0;
                border-radius: 6px;
                background: {c['text_primary']};
            }}
            #timeLabel {{
                color: {c['text_muted']};
                font-size: {f['size_xs']}px;
                min-width: 36px;
            }}
        """)

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _fmt(ms: int) -> str:
        s = ms // 1000
        return f"{s // 60}:{s % 60:02d}"

    def _on_seek(self, value: int) -> None:
        if self._duration_ms > 0:
            self.seek_requested.emit(int(value / 10_000 * self._duration_ms))

    # ── public API ────────────────────────────────────────────────────────────

    def update_state(self, state: PlayerState) -> None:
        track = state.current_track
        if track:
            self._title.setText(track.title)
            self._artist.setText(track.artist)
            self._duration_ms = state.duration_ms
            self._dur_label.setText(self._fmt(state.duration_ms))
            if state.status == "loading":
                # New track starting — reset position display immediately
                self._cover.setPixmap(QPixmap())
                self._progress.setValue(0)
                self._pos_label.setText("0:00")
        else:
            self._title.setText("—")
            self._artist.setText("—")
            self._duration_ms = 0
            self._dur_label.setText("0:00")
            self._progress.setValue(0)
            self._pos_label.setText("0:00")
            self._cover.setPixmap(QPixmap())
        self._play_btn.setText("⏸" if state.status == "playing" else "▶")
        self._shuffle_btn.setChecked(state.shuffle)
        self._repeat_btn.setChecked(state.repeat_mode != "none")
        repeat_icons = {"none": "↻", "all": "↻", "one": "↺"}
        self._repeat_btn.setText(repeat_icons.get(state.repeat_mode, "↻"))

    def update_position(self, position_ms: int) -> None:
        self._pos_label.setText(self._fmt(position_ms))
        if self._duration_ms > 0 and not self._progress.isSliderDown():
            self._progress.setValue(int(position_ms / self._duration_ms * 10_000))

    def set_volume(self, volume: int) -> None:
        self._volume.setValue(volume)

    def set_lyrics_active(self, active: bool) -> None:
        self._lyrics_btn.setChecked(active)

    def set_cover_pixmap_from_bytes(self, data: bytes) -> None:
        """Scale image bytes to 48×48 with rounded corners and display."""
        px = QPixmap()
        if not px.loadFromData(data):
            return
        px = px.scaled(
            48, 48,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        # Crop to exact 48×48 from center
        if px.width() > 48 or px.height() > 48:
            x = (px.width() - 48) // 2
            y = (px.height() - 48) // 2
            px = px.copy(x, y, 48, 48)
        # Round corners to match CSS border-radius: 6px
        rounded = QPixmap(48, 48)
        rounded.fill(Qt.GlobalColor.transparent)
        painter = QPainter(rounded)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, 48, 48, 6, 6)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, px)
        painter.end()
        self._cover.setPixmap(rounded)
