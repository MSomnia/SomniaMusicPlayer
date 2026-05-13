from __future__ import annotations
from abc import ABC, abstractmethod
from core.models import Track, Playlist, Album, LyricLine


class AbstractPlatform(ABC):
    platform_id: str  # "spotify" | "ytmusic" | "netease"

    @abstractmethod
    async def is_authenticated(self) -> bool: ...

    @abstractmethod
    async def search(self, query: str, limit: int = 30) -> list[Track]: ...

    @abstractmethod
    async def get_stream_url(self, track: Track) -> str: ...

    @abstractmethod
    async def get_lyrics(self, track: Track) -> list[LyricLine]: ...

    @abstractmethod
    async def get_library_playlists(self) -> list[Playlist]: ...

    async def get_home(self) -> list[tuple[str, list[Track]]]:
        """Return home-page sections as [(section_title, tracks)]."""
        return []

    async def get_playlist_tracks(self, playlist_id: str) -> list[Track]:
        """Return tracks in the given playlist."""
        return []

    async def get_recommendations(self, track: Track) -> list[Track]:
        """Return recommended tracks based on *track* for autoplay."""
        return []

    async def search_albums(self, query: str, limit: int = 5) -> list[Album]:
        """Return albums matching *query*."""
        return []

    async def get_album_tracks(self, album_id: str) -> list[Track]:
        """Return tracks in the given album."""
        return []
