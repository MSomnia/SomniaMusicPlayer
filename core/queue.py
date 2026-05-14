from __future__ import annotations
import random
from core.models import Track


class PlayQueue:
    def __init__(self) -> None:
        self._tracks: list[Track] = []
        self._index: int = -1

    @property
    def tracks(self) -> list[Track]:
        return self._tracks

    @property
    def current_index(self) -> int:
        return self._index

    @property
    def current_track(self) -> Track | None:
        if 0 <= self._index < len(self._tracks):
            return self._tracks[self._index]
        return None

    def set_tracks(self, tracks: list[Track], start_index: int = 0) -> None:
        self._tracks = list(tracks)
        self._index = start_index if tracks else -1

    def add(self, track: Track) -> None:
        self._tracks.append(track)
        if self._index == -1:
            self._index = 0

    def next(self, repeat_mode: str = "none") -> Track | None:
        if not self._tracks:
            return None
        if repeat_mode == "one":
            return self.current_track
        nxt = self._index + 1
        if nxt >= len(self._tracks):
            if repeat_mode == "all":
                nxt = 0
            else:
                return None
        self._index = nxt
        return self.current_track

    def peek_next(self, repeat_mode: str = "none") -> Track | None:
        """Return the next track without advancing the index."""
        if not self._tracks:
            return None
        if repeat_mode == "one":
            return self.current_track
        nxt = self._index + 1
        if nxt >= len(self._tracks):
            if repeat_mode == "all":
                return self._tracks[0]
            return None
        return self._tracks[nxt]

    def previous(self) -> Track | None:
        if not self._tracks:
            return None
        self._index = max(0, self._index - 1)
        return self.current_track

    def shuffle(self) -> None:
        if not self._tracks:
            return
        current = self.current_track
        random.shuffle(self._tracks)
        if current is not None:
            self._index = self._tracks.index(current)

    def clear(self) -> None:
        self._tracks = []
        self._index = -1

    def __len__(self) -> int:
        return len(self._tracks)
