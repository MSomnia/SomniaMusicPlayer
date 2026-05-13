from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QSizePolicy, QGraphicsOpacityEffect,
)
from PyQt6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, QTimer, pyqtSignal,
)
from PyQt6.QtGui import (
    QPainter, QPixmap, QPainterPath, QColor, QRadialGradient, QCursor,
)
from core.lyrics_engine import LyricsEngine
from core.models import LyricLine, PlayerState
from ui.theme import COLORS, FONTS


class _StandbyLyricLine(QLabel):
    def __init__(self, line: LyricLine, parent=None) -> None:
        super().__init__(parent)
        self._line = line
        self._is_current = False
        self._word_idx = -1
        self.setWordWrap(True)
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setContentsMargins(0, 4, 0, 4)
        self._render()

    def set_state(self, is_current: bool, word_idx: int = -1) -> None:
        if self._is_current == is_current and self._word_idx == word_idx:
            return
        self._is_current = is_current
        self._word_idx = word_idx
        self._render()

    @staticmethod
    def _esc(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _render(self) -> None:
        if self._is_current:
            self.setStyleSheet(
                f"font-size: {FONTS['size_lyrics']}px; font-weight: bold;"
                " background: transparent;"
            )
            if self._line.words:
                parts: list[str] = []
                for i, word in enumerate(self._line.words):
                    if i < self._word_idx:
                        color = COLORS["lyrics_past"]
                    elif i == self._word_idx:
                        color = COLORS["accent"]
                    else:
                        color = COLORS["lyrics_future"]
                    parts.append(
                        f'<span style="color:{color};">{self._esc(word.text)}</span>'
                    )
                self.setText("".join(parts))
            else:
                color = COLORS["lyrics_active"]
                self.setText(
                    f'<span style="color:{color};">{self._esc(self._line.text)}</span>'
                )
        else:
            self.setStyleSheet(
                f"font-size: {FONTS['size_lg']}px; font-weight: normal;"
                " background: transparent;"
            )
            color = COLORS["lyrics_future"]
            self.setText(
                f'<span style="color:{color};">{self._esc(self._line.text)}</span>'
            )


class StandbyPage(QWidget):
    def __init__(self, ctrl, parent=None) -> None:
        super().__init__(parent)
        self._ctrl = ctrl
        self._engine = LyricsEngine()
        self._gradient_rgb: tuple[int, int, int] = (80, 60, 120)
        self._line_widgets: list[_StandbyLyricLine] = []
        self._current_line: int = -1
        self._last_position_ms: int = 0
        self._scroll_anim: QPropertyAnimation | None = None
        self._fade_anim: QPropertyAnimation | None = None
        self._pending_scroll: int | None = None
        self.setAutoFillBackground(False)
        self._setup_ui()
        self._apply_styles()
        self.hide()

    def _setup_ui(self) -> None:
        # ── Main horizontal split ─────────────────────────────────────────────
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Left panel ────────────────────────────────────────────────────────
        left = QWidget()
        left.setObjectName("standbyLeft")
        left.setAutoFillBackground(False)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(40, 72, 40, 40)
        left_layout.setSpacing(0)
        left_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)

        # Cover image
        self._cover_label = QLabel()
        self._cover_label.setObjectName("standbyCover")
        self._cover_label.setFixedSize(130, 130)
        self._cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(self._cover_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        left_layout.addSpacing(12)

        # Song title
        self._title_label = QLabel("暂无播放")
        self._title_label.setObjectName("standbyTitle")
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title_label.setWordWrap(True)
        left_layout.addWidget(self._title_label)
        left_layout.addSpacing(4)

        # Artist
        self._artist_label = QLabel("—")
        self._artist_label.setObjectName("standbyArtist")
        self._artist_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(self._artist_label)
        left_layout.addSpacing(16)

        # Divider
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setObjectName("standbyDivider")
        left_layout.addWidget(divider)
        left_layout.addSpacing(16)

        # "No lyrics" placeholder
        self._no_lyrics_label = QLabel("暂无歌词")
        self._no_lyrics_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_lyrics_label.setStyleSheet(
            f"color: {COLORS['text_muted']};"
            f" font-size: {FONTS['size_lg']}px;"
            " background: transparent;"
        )

        # Lyrics scroll area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("background: transparent; border: none;")
        self._scroll.viewport().setStyleSheet("background: transparent;")

        self._lyric_container = QWidget()
        self._lyric_container.setStyleSheet("background: transparent;")
        self._lyric_layout = QVBoxLayout(self._lyric_container)
        self._lyric_layout.setContentsMargins(0, 40, 0, 80)
        self._lyric_layout.setSpacing(12)
        self._lyric_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._scroll.setWidget(self._lyric_container)

        left_layout.addWidget(self._scroll, stretch=1)
        left_layout.addWidget(self._no_lyrics_label, stretch=1)
        self._set_mode_no_lyrics()

        # ── Right panel ───────────────────────────────────────────────────────
        right = QWidget()
        right.setObjectName("standbyRight")
        right.setAutoFillBackground(False)
        right_layout = QVBoxLayout(right)
        right_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        placeholder = QLabel("✦\n更多内容\n即将到来")
        placeholder.setObjectName("standbyPlaceholder")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_layout.addWidget(placeholder)

        root.addWidget(left, stretch=1)
        root.addWidget(right, stretch=1)

        # ── Close button (absolute overlay) ───────────────────────────────────
        self._close_btn = QPushButton("✕  退出待机", self)
        self._close_btn.setObjectName("standbyCloseBtn")
        self._close_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._close_btn.setFixedSize(116, 32)
        self._close_btn.clicked.connect(self.leave)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._close_btn.move(12, 12)

    def _apply_styles(self) -> None:
        c, f = COLORS, FONTS
        self.setStyleSheet(f"""
            #standbyLeft, #standbyRight {{
                background: transparent;
            }}
            #standbyTitle {{
                color: {c['text_primary']};
                font-size: {f['size_xl']}px;
                font-weight: bold;
            }}
            #standbyArtist {{
                color: rgba(255,255,255,0.55);
                font-size: {f['size_sm']}px;
            }}
            #standbyDivider {{
                color: rgba(255,255,255,0.08);
                max-height: 1px;
                margin: 0 15%;
            }}
            #standbyPlaceholder {{
                color: rgba(255,255,255,0.18);
                font-size: {f['size_md']}px;
                line-height: 2;
            }}
            #standbyCloseBtn {{
                background: rgba(255,255,255,0.10);
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 16px;
                color: rgba(255,255,255,0.70);
                font-size: {f['size_xs']}px;
                padding: 0 14px;
            }}
            #standbyCloseBtn:hover {{
                background: rgba(255,255,255,0.18);
                color: {c['text_primary']};
            }}
        """)

    def _set_mode_lyrics(self) -> None:
        self._scroll.show()
        self._no_lyrics_label.hide()

    def _set_mode_no_lyrics(self) -> None:
        self._scroll.hide()
        self._no_lyrics_label.show()

    # ── Public API ────────────────────────────────────────────────────────────

    def on_state_changed(self, state: PlayerState) -> None:
        track = state.current_track
        if track is None:
            self._title_label.setText("暂无播放")
            self._artist_label.setText("—")
            self._set_placeholder_cover()
        else:
            self._title_label.setText(track.title)
            self._artist_label.setText(track.artist)
            if state.status == "loading":
                self._set_loading_cover()

    def set_cover_art_bytes(self, data: bytes) -> None:
        pixmap = QPixmap()
        if data and pixmap.loadFromData(data):
            self._draw_cover(pixmap)
        else:
            self._set_placeholder_cover()

    def _draw_cover(self, pixmap: QPixmap) -> None:
        size = 130
        scaled = pixmap.scaled(
            size, size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        rounded = QPixmap(size, size)
        rounded.fill(Qt.GlobalColor.transparent)
        p = QPainter(rounded)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, size, size, 10, 10)
        p.setClipPath(path)
        x = (size - scaled.width()) // 2
        y = (size - scaled.height()) // 2
        p.drawPixmap(x, y, scaled)
        p.end()
        self._cover_label.setPixmap(rounded)
        self._cover_label.setText("")
        self._cover_label.setStyleSheet("")

    def _set_placeholder_cover(self) -> None:
        self._cover_label.setPixmap(QPixmap())
        self._cover_label.setText("🎵")
        self._cover_label.setStyleSheet(
            "font-size: 48px;"
            " background: rgba(255,255,255,0.08);"
            " border-radius: 10px;"
        )

    def _set_loading_cover(self) -> None:
        self._cover_label.setPixmap(QPixmap())
        self._cover_label.setText("")
        self._cover_label.setStyleSheet(
            "background: rgba(255,255,255,0.08);"
            " border-radius: 10px;"
        )

    def set_cover_color(self, r: int, g: int, b: int) -> None:
        self._gradient_rgb = (r, g, b)
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Black base
        painter.fillRect(self.rect(), Qt.GlobalColor.black)

        # Background image (from _AppRoot parent)
        parent = self.parent()
        if parent is not None and hasattr(parent, "background_pixmap"):
            bg: QPixmap = parent.background_pixmap()
            if not bg.isNull():
                scaled = bg.scaled(
                    self.size(),
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                x = (self.width() - scaled.width()) // 2
                y = (self.height() - scaled.height()) // 2
                painter.drawPixmap(x, y, scaled)

        # Ambient overlay: rgba(0,0,0,0.25) → alpha ≈ 64
        painter.fillRect(self.rect(), QColor(0, 0, 0, 64))

        # Cover glow: radial gradient centred on the left half
        r, g, b = self._gradient_rgb
        cx = self.width() // 4
        cy = int(self.height() * 0.42)
        radius = int(self.width() * 0.35)
        grad = QRadialGradient(cx, cy, radius)
        grad.setColorAt(0.0, QColor(r, g, b, 77))   # opacity ≈ 0.30
        grad.setColorAt(1.0, QColor(r, g, b, 0))
        painter.fillRect(self.rect(), grad)

    def set_lyrics(self, lines: list[LyricLine]) -> None:
        self._engine.load(lines)
        self._current_line = -1
        self._rebuild_line_widgets()
        if lines:
            self._set_mode_lyrics()
            if self._last_position_ms > 0:
                QTimer.singleShot(0, lambda: self.update_position(self._last_position_ms))
        else:
            self._set_mode_no_lyrics()

    def update_position(self, position_ms: int) -> None:
        self._last_position_ms = position_ms
        if not self.isVisible() or not self._line_widgets:
            return
        line_idx, word_idx = self._engine.update(position_ms)
        line_changed = line_idx != self._current_line
        for i, widget in enumerate(self._line_widgets):
            widget.set_state(i == line_idx, word_idx if i == line_idx else -1)
        if line_changed:
            self._current_line = line_idx
            if line_idx >= 0:
                self._pending_scroll = line_idx
                QTimer.singleShot(0, self._do_pending_scroll)

    def _rebuild_line_widgets(self) -> None:
        for w in self._line_widgets:
            self._lyric_layout.removeWidget(w)
            w.deleteLater()
        self._line_widgets.clear()
        for line in self._engine.lines:
            label = _StandbyLyricLine(line)
            label.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
            )
            self._lyric_layout.addWidget(label)
            self._line_widgets.append(label)

    def _do_pending_scroll(self) -> None:
        if self._pending_scroll is None:
            return
        line_idx = self._pending_scroll
        self._pending_scroll = None
        self._scroll_to_line(line_idx)

    def _scroll_to_line(self, line_idx: int) -> None:
        if line_idx < 0 or line_idx >= len(self._line_widgets):
            return
        target_widget = self._line_widgets[line_idx]
        widget_center = target_widget.y() + target_widget.height() // 2
        viewport_center = self._scroll.viewport().height() // 2
        target_value = widget_center - viewport_center
        sb = self._scroll.verticalScrollBar()
        target_value = max(0, min(target_value, sb.maximum()))
        if self._scroll_anim and self._scroll_anim.state() == QPropertyAnimation.State.Running:
            self._scroll_anim.stop()
        self._scroll_anim = QPropertyAnimation(sb, b"value", self)
        self._scroll_anim.setDuration(450)
        self._scroll_anim.setStartValue(sb.value())
        self._scroll_anim.setEndValue(target_value)
        self._scroll_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._scroll_anim.start()

    def enter(self) -> None:
        if self._fade_anim is not None and self._fade_anim.state() == QPropertyAnimation.State.Running:
            self._fade_anim.stop()

        effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(effect)
        effect.setOpacity(0.0)

        self.show()
        self.raise_()

        self._fade_anim = QPropertyAnimation(effect, b"opacity", self)
        self._fade_anim.setDuration(300)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_anim.start()

    def leave(self) -> None:
        if self._fade_anim is not None and self._fade_anim.state() == QPropertyAnimation.State.Running:
            self._fade_anim.stop()

        effect = self.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(self)
            self.setGraphicsEffect(effect)

        start_opacity = effect.opacity() if isinstance(effect, QGraphicsOpacityEffect) else 1.0

        self._fade_anim = QPropertyAnimation(effect, b"opacity", self)
        self._fade_anim.setDuration(200)
        self._fade_anim.setStartValue(start_opacity)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._fade_anim.finished.connect(self.hide)
        self._fade_anim.start()
