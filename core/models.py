from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Track:
    id: str
    platform: str           # "spotify" | "ytmusic" | "netease"
    title: str
    artist: str
    artists: list[str]
    album: str
    album_cover_url: str
    duration_ms: int
    is_explicit: bool = False
    stream_url: str | None = None


@dataclass
class LyricWord:
    start_ms: int
    end_ms: int
    text: str


@dataclass
class LyricLine:
    start_ms: int
    end_ms: int
    text: str
    words: list[LyricWord] = field(default_factory=list)


@dataclass
class Playlist:
    id: str
    platform: str
    name: str
    cover_url: str
    track_count: int
    tracks: list[Track] = field(default_factory=list)


@dataclass
class PlayerState:
    status: str = "idle"        # "idle" | "loading" | "playing" | "paused" | "error"
    current_track: Track | None = None
    position_ms: int = 0
    duration_ms: int = 0
    volume: int = 70
    shuffle: bool = False
    repeat_mode: str = "none"   # "none" | "one" | "all"
    queue: list[Track] = field(default_factory=list)
    queue_index: int = -1
