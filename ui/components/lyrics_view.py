from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QFrame, QSizePolicy, QPushButton,
)
from PyQt6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, QTimer, pyqtSignal, QSize,
)
from PyQt6.QtGui import (
    QPainter, QLinearGradient, QColor, QCursor, QPixmap, QPainterPath,
)

from core.lyrics_engine import LyricsEngine
from core.models import LyricLine
from ui.theme import COLORS, FONTS


class _LineLabel(QLabel):
    """Single lyric line that can display word-level coloring when active."""

    def __init__(self, line: LyricLine, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._line = line
        self._is_current = False
        self._word_idx = -1
        self.setWordWrap(True)
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.setContentsMargins(0, 6, 0, 6)
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


class LyricsView(QWidget):
    """Scrollable lyrics view with per-word highlight and gradient background.

    Public API
    ----------
    set_lyrics(lines)       — load a new set of lyric lines
    update_position(ms)     — advance the highlight to the given playback position
    set_cover_color(r,g,b)  — update the gradient accent color
    clear()                 — reset to "暂无歌词" state

    Signals
    -------
    back_requested          — emitted when the user clicks the back button
    """

    back_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._engine = LyricsEngine()
        self._gradient_rgb: tuple[int, int, int] = (0x0D, 0x0D, 0x0D)
        self._cover_pixmap: QPixmap | None = None
        self._blurred_cover: QPixmap | None = None
        self._blurred_cover_size: QSize | None = None
        self._line_widgets: list[_LineLabel] = []
        self._current_line: int = -1
        self._last_position_ms: int = 0   # remember position between lyrics loads
        self._scroll_anim: QPropertyAnimation | None = None
        self._pending_scroll: int | None = None
        self.setAutoFillBackground(False)
        self._setup_ui()

    # ── construction ──────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header bar with back button
        header = QWidget()
        header.setFixedHeight(52)
        header.setStyleSheet("background: transparent;")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 8, 16, 8)
        hl.setSpacing(0)

        self._back_btn = QPushButton("← 返回")
        self._back_btn.setObjectName("lyricsBackBtn")
        self._back_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._back_btn.clicked.connect(self.back_requested)
        hl.addWidget(self._back_btn)
        hl.addStretch()

        root.addWidget(header)

        # "No lyrics" placeholder
        self._no_lyrics_label = QLabel("暂无歌词")
        self._no_lyrics_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_lyrics_label.setStyleSheet(
            f"color: {COLORS['text_muted']};"
            f" font-size: {FONTS['size_lg']}px;"
            " background: transparent;"
        )

        # Scroll area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._scroll.setStyleSheet("background: transparent; border: none;")
        self._scroll.viewport().setStyleSheet("background: transparent;")

        # Container for line widgets
        self._container = QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(80, 80, 80, 120)
        self._container_layout.setSpacing(12)
        self._container_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._scroll.setWidget(self._container)

        root.addWidget(self._scroll, stretch=1)
        root.addWidget(self._no_lyrics_label, stretch=1)
        self._set_mode_no_lyrics()

        self._apply_styles()

    def _apply_styles(self) -> None:
        self.setStyleSheet(f"""
            #lyricsBackBtn {{
                background: transparent;
                border: none;
                color: {COLORS['text_secondary']};
                font-size: {FONTS['size_sm']}px;
                padding: 4px 8px 4px 0;
                text-align: left;
            }}
            #lyricsBackBtn:hover {{
                color: {COLORS['text_primary']};
            }}
        """)

    # ── painting ──────────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(self.rect().toRectF(), 8, 8)
        painter.setClipPath(path)
        painter.fillPath(path, QColor(COLORS["bg_base"]))

        cover = self._blurred_cover_for_size(self.size())
        if cover is not None:
            painter.setOpacity(0.5)
            painter.drawPixmap(0, 0, cover)
            painter.setOpacity(1.0)

        r, g, b = self._gradient_rgb
        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0.0, QColor(r, g, b, 90 if cover else 140))
        grad.setColorAt(0.6, QColor(0x0D, 0x0D, 0x0D, 190 if cover else 230))
        grad.setColorAt(1.0, QColor(0x0D, 0x0D, 0x0D, 245 if cover else 255))
        painter.fillPath(path, grad)

    # ── public API ────────────────────────────────────────────────────────────

    def set_lyrics(self, lines: list[LyricLine]) -> None:
        self._engine.load(lines)
        self._current_line = -1
        self._rebuild_line_widgets()
        if lines:
            self._set_mode_lyrics()
            # Immediately highlight the line matching the already-known position
            if self._last_position_ms > 0:
                QTimer.singleShot(0, lambda: self.update_position(self._last_position_ms))
        else:
            self._set_mode_no_lyrics()

    def update_position(self, position_ms: int) -> None:
        self._last_position_ms = position_ms
        if not self._line_widgets:
            return
        line_idx, word_idx = self._engine.update(position_ms)

        line_changed = line_idx != self._current_line

        for i, widget in enumerate(self._line_widgets):
            is_current = i == line_idx
            w_idx = word_idx if is_current else -1
            widget.set_state(is_current, w_idx)

        if line_changed:
            self._current_line = line_idx
            if line_idx >= 0:
                self._pending_scroll = line_idx
                QTimer.singleShot(0, self._do_pending_scroll)

    def set_cover_color(self, r: int, g: int, b: int) -> None:
        self._gradient_rgb = (r, g, b)
        self.update()

    def set_cover_art_bytes(self, data: bytes) -> None:
        pixmap = QPixmap()
        if not data or not pixmap.loadFromData(data):
            self.clear_cover_art()
            return
        self._cover_pixmap = pixmap
        self._blurred_cover = None
        self._blurred_cover_size = None
        self.update()

    def clear_cover_art(self) -> None:
        self._cover_pixmap = None
        self._blurred_cover = None
        self._blurred_cover_size = None
        self.update()

    def clear(self) -> None:
        self._engine.clear()
        self._current_line = -1
        self._last_position_ms = 0
        self.clear_cover_art()
        self._rebuild_line_widgets()
        self._set_mode_no_lyrics()

    # ── private helpers ───────────────────────────────────────────────────────

    def _set_mode_lyrics(self) -> None:
        self._scroll.show()
        self._no_lyrics_label.hide()

    def _set_mode_no_lyrics(self) -> None:
        self._scroll.hide()
        self._no_lyrics_label.show()

    def _rebuild_line_widgets(self) -> None:
        for w in self._line_widgets:
            self._container_layout.removeWidget(w)
            w.deleteLater()
        self._line_widgets.clear()

        for line in self._engine.lines:
            label = _LineLabel(line)
            label.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
            )
            self._container_layout.addWidget(label)
            self._line_widgets.append(label)

    def _blurred_cover_for_size(self, size: QSize) -> QPixmap | None:
        if (
            self._cover_pixmap is None
            or self._cover_pixmap.isNull()
            or size.width() <= 0
            or size.height() <= 0
        ):
            return None
        if (
            self._blurred_cover is not None
            and self._blurred_cover_size == size
            and not self._blurred_cover.isNull()
        ):
            return self._blurred_cover

        w, h = size.width(), size.height()
        scaled = self._cover_pixmap.scaled(
            w,
            h,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = max(0, (scaled.width() - w) // 2)
        y = max(0, (scaled.height() - h) // 2)
        cropped = scaled.copy(x, y, w, h)

        blur_w = max(1, w // 48)
        blur_h = max(1, h // 48)
        small = cropped.scaled(
            blur_w,
            blur_h,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._blurred_cover = small.scaled(
            w,
            h,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._blurred_cover_size = QSize(size.width(), size.height())
        return self._blurred_cover

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
