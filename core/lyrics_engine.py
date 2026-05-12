from __future__ import annotations
import bisect
from core.models import LyricLine


class LyricsEngine:
    """Maps playback position to current lyric line and word index."""

    def __init__(self) -> None:
        self._lines: list[LyricLine] = []
        self._starts: list[int] = []
        self._line_idx: int = -1
        self._word_idx: int = -1

    def load(self, lines: list[LyricLine]) -> None:
        self._lines = lines
        self._starts = [l.start_ms for l in lines]
        self._line_idx = -1
        self._word_idx = -1

    def clear(self) -> None:
        self.load([])

    @property
    def lines(self) -> list[LyricLine]:
        return self._lines

    @property
    def current_line(self) -> int:
        return self._line_idx

    @property
    def current_word(self) -> int:
        return self._word_idx

    def update(self, position_ms: int) -> tuple[int, int]:
        """Return (line_idx, word_idx) for position_ms; -1 means none active."""
        if not self._lines:
            return -1, -1

        # Rightmost line whose start_ms <= position_ms
        idx = bisect.bisect_right(self._starts, position_ms) - 1

        if idx < 0 or self._lines[idx].end_ms <= position_ms:
            self._line_idx = -1
            self._word_idx = -1
            return -1, -1

        self._line_idx = idx

        # Word-level search within the line
        line = self._lines[idx]
        word_idx = -1
        if line.words:
            word_starts = [w.start_ms for w in line.words]
            widx = bisect.bisect_right(word_starts, position_ms) - 1
            if widx >= 0 and line.words[widx].end_ms > position_ms:
                word_idx = widx

        self._word_idx = word_idx
        return self._line_idx, self._word_idx
