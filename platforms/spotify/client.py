from __future__ import annotations
import asyncio
import base64
import json
import logging
import re
import time
from uuid import uuid4

import httpx

from core.models import LyricLine, Playlist, Track
from platforms.base import AbstractPlatform

logger = logging.getLogger(__name__)

_WEB_API_URL = "https://api.spotify.com/v1"
_PARTNER_URL = "https://api-partner.spotify.com/pathfinder/v2/query"
_CLIENT_TOKEN_URL = "https://clienttoken.spotify.com/v1/clienttoken"
_SPOTIFY_WEB_URL = "https://open.spotify.com/"
_WEB_CLIENT_ID = "d8a5ed958d274c2e8ee717e6a4b0971d"
_WEB_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_SEARCH_SUGGESTIONS_HASH = "556f5a15b2fdd3a7113ffd377ad9805e38a3a27b8bb1ca7d6d76bad54aa8ee12"
_APP_HEADERS = {
    "App-Platform": "WebPlayer",
    "Spotify-App-Version": "1.2.50.248",
}


def _parse_partner_hashes(source: str) -> dict[str, str]:
    """Return {operationName: sha256Hash} from a Spotify web-player JS bundle.

    Spotify stores persisted-query hashes as constructor calls:
        new X("operationName", "query", "<64-hex-hash>", null)
    """
    result: dict[str, str] = {}
    for m in re.finditer(
        r'new\s+\w[\w$.]*\s*\(\s*"([^"]{2,60})"\s*,\s*"(?:query|mutation)"\s*,\s*"([0-9a-f]{64})"\s*,\s*null\s*\)',
        source,
    ):
        result[m.group(1)] = m.group(2)
    return result


class SpotifyClient(AbstractPlatform):
    platform_id = "spotify"

    # Class-level cache: operation hashes survive across method calls
    _op_hash_cache: dict[str, str] = {}

    def __init__(self, auth: "SpotifyAuth") -> None:
        self._auth = auth
        self._search_cache: dict[tuple[str, int], tuple[float, list[Track]]] = {}
        self._rate_limited_until: float = 0.0
        self._client_token: str | None = None
        self._client_version: str | None = None
        self._device_id = uuid4().hex

    async def is_authenticated(self) -> bool:
        return bool(await self._auth.load_sp_dc())

    async def search(self, query: str, limit: int = 30) -> list[Track]:
        query = query.strip()
        if not query:
            return []
        cache_key = (query.lower(), limit)
        now = time.time()
        cached = self._search_cache.get(cache_key)
        if cached and now - cached[0] < 60:
            return cached[1]
        if now < self._rate_limited_until:
            wait = int(self._rate_limited_until - now)
            logger.warning("Spotify search is rate limited; retry after %ss", wait)
            return []

        try:
            token = await self._auth.get_access_token()
        except Exception as exc:
            logger.warning("Spotify auth error during search: %s", exc)
            return []

        try:
            async with httpx.AsyncClient() as http:
                client_token = await self._get_client_token(http)
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json;charset=UTF-8",
                    "Origin": "https://open.spotify.com",
                    "Referer": "https://open.spotify.com/",
                    "User-Agent": _WEB_UA,
                    **_APP_HEADERS,
                }
                if client_token:
                    headers["client-token"] = client_token
                resp = await http.post(
                    _PARTNER_URL,
                    json={
                        "variables": {
                            "query": query,
                            "limit": min(limit, 30),
                            "numberOfTopResults": min(limit, 30),
                            "offset": 0,
                            "includeAuthors": False,
                            "includeAlbumPreReleases": False,
                            "includeEpisodeContentRatingsV2": False,
                        },
                        "operationName": "searchSuggestions",
                        "extensions": {
                            "persistedQuery": {
                                "version": 1,
                                "sha256Hash": _SEARCH_SUGGESTIONS_HASH,
                            }
                        },
                    },
                    headers=headers,
                    timeout=10.0,
                )
                resp.raise_for_status()
                tracks = self._parse_search_suggestions(resp.json())
                self._search_cache[cache_key] = (time.time(), tracks)
                return tracks
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                retry_after = _retry_after_seconds(exc.response)
                self._rate_limited_until = time.time() + retry_after
                logger.warning("Spotify search rate limited; retry after %ss", retry_after)
                await asyncio.sleep(min(retry_after, 2))
                return []
            logger.warning("Spotify search failed: %s", exc)
            return []
        except Exception as exc:
            logger.warning("Spotify search failed: %s", exc)
            return []

    async def _get_client_token(self, http: httpx.AsyncClient) -> str | None:
        if self._client_token:
            return self._client_token
        version = await self._get_client_version(http)
        payload = {
            "client_data": {
                "client_version": version,
                "client_id": _WEB_CLIENT_ID,
                "js_sdk_data": {
                    "device_brand": "unknown",
                    "device_model": "desktop",
                    "os": "windows",
                    "os_version": "NT 10.0",
                    "device_id": self._device_id,
                    "device_type": "computer",
                },
            }
        }
        try:
            resp = await http.post(
                _CLIENT_TOKEN_URL,
                json=payload,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Origin": "https://open.spotify.com",
                    "Referer": "https://open.spotify.com/",
                    "User-Agent": _WEB_UA,
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            self._client_token = (resp.json().get("granted_token") or {}).get("token")
            if not self._client_token:
                logger.warning("Spotify client-token response missing token")
            return self._client_token
        except Exception as exc:
            logger.warning("Spotify client-token fetch failed: %s", exc)
            return None

    async def _get_client_version(self, http: httpx.AsyncClient) -> str:
        if self._client_version:
            return self._client_version
        try:
            resp = await http.get(
                _SPOTIFY_WEB_URL,
                headers={"User-Agent": _WEB_UA, "Accept": "text/html"},
                timeout=10.0,
            )
            resp.raise_for_status()
            match = re.search(
                r'<script id="appServerConfig" type="text/plain">([^<]+)</script>',
                resp.text,
            )
            if match:
                data = json.loads(base64.b64decode(match.group(1)).decode("utf-8"))
                version = data.get("clientVersion")
                if version:
                    self._client_version = version
                    return version
        except Exception as exc:
            logger.warning("Spotify client version fetch failed: %s", exc)
        self._client_version = "1.2.90.356.gc7ecdb13"
        return self._client_version

    async def _get_partner_hash(self, http: httpx.AsyncClient, op: str) -> str | None:
        """Return the persisted-query SHA256 for *op*, loading from the web-player bundle if needed.

        The bundle is fetched once and all discovered hashes are cached at the class
        level so subsequent calls for any operation are instant.
        """
        cache = SpotifyClient._op_hash_cache
        if op in cache:
            return cache[op]

        try:
            resp = await http.get(
                _SPOTIFY_WEB_URL,
                headers={"User-Agent": _WEB_UA, "Accept": "text/html"},
                timeout=10.0,
            )
            resp.raise_for_status()
            bundle_urls = list(dict.fromkeys(
                re.findall(r'https://[^"\'<>\s]+/web-player\.[^"\'<>\s]+\.js', resp.text)
            ))
            for url in bundle_urls[:8]:
                try:
                    js = await http.get(
                        url,
                        headers={"User-Agent": _WEB_UA, "Accept": "*/*"},
                        timeout=20.0,
                    )
                    js.raise_for_status()
                    found = _parse_partner_hashes(js.text)
                    cache.update(found)
                    logger.debug("Spotify partner hashes: found %d ops from %s…", len(found), url[-40:])
                    if op in cache:
                        return cache[op]
                except Exception as exc:
                    logger.debug("Spotify bundle fetch failed: %s", exc)
        except Exception as exc:
            logger.warning("Spotify partner hash extraction failed: %s", exc)

        return cache.get(op)

    def _partner_headers(self, token: str, client_token: str | None) -> dict:
        h = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json;charset=UTF-8",
            "Origin": "https://open.spotify.com",
            "Referer": "https://open.spotify.com/",
            "User-Agent": _WEB_UA,
            **_APP_HEADERS,
        }
        if client_token:
            h["client-token"] = client_token
        return h

    async def get_stream_url(self, track: Track) -> str:
        return f"spotify:track:{track.id}"

    async def get_lyrics(self, track: Track) -> list[LyricLine]:
        from platforms.spotify.lyrics import SpotifyLyrics

        try:
            token = await self._auth.get_access_token()
        except Exception as exc:
            logger.warning("Spotify auth error during lyrics fetch: %s", exc)
            return []

        async with httpx.AsyncClient() as http:
            return await SpotifyLyrics(http).fetch(track.id, token)

    async def get_home(self) -> list[tuple[str, list[Track]]]:
        """Return home-page sections via the partner API.

        The home query returns Albums/Playlists, so we load tracks from the
        first playlist in each section. Limited to 3 sections to keep latency low.
        """
        try:
            token = await self._auth.get_access_token()
            async with httpx.AsyncClient() as http:
                client_token = await self._get_client_token(http)
                home_hash = await self._get_partner_hash(http, "home")
                pl_hash = await self._get_partner_hash(http, "fetchPlaylist")
                if not home_hash:
                    logger.warning("Spotify home: 'home' operation hash not found in bundle")
                    return []

                # Step 1: fetch home sections
                resp = await http.post(
                    _PARTNER_URL,
                    json={
                        "variables": {
                            "timeZone": "UTC",
                            "sp_t": "",
                            "facet": "",
                            "sectionItemsLimit": 8,
                            "includeEpisodeContentRatingsV2": False,
                            "homeEndUserIntegration": "INTEGRATION_WEB_PLAYER",
                        },
                        "operationName": "home",
                        "extensions": {"persistedQuery": {"version": 1, "sha256Hash": home_hash}},
                    },
                    headers=self._partner_headers(token, client_token),
                    timeout=15.0,
                )
                resp.raise_for_status()

                # Step 2: extract (section_title, playlist_uri) pairs
                section_playlists = self._extract_home_playlists(resp.json())
                if not section_playlists:
                    return []
                if not pl_hash:
                    logger.warning("Spotify home: 'fetchPlaylist' hash not found; returning empty")
                    return []

                # Step 3: load tracks from first playlist in each section (max 3 sections)
                result: list[tuple[str, list[Track]]] = []
                for title, pl_uri in section_playlists[:3]:
                    try:
                        pl_resp = await http.post(
                            _PARTNER_URL,
                            json={
                                "variables": {
                                    "uri": pl_uri,
                                    "offset": 0,
                                    "limit": 20,
                                    "enableWatchFeedEntrypoint": False,
                                },
                                "operationName": "fetchPlaylist",
                                "extensions": {"persistedQuery": {"version": 1, "sha256Hash": pl_hash}},
                            },
                            headers=self._partner_headers(token, client_token),
                            timeout=10.0,
                        )
                        pl_resp.raise_for_status()
                        tracks = self._parse_fetch_playlist(pl_resp.json())
                        if tracks:
                            result.append((title, tracks))
                    except Exception as exc:
                        logger.debug("Spotify home playlist load failed: %s", exc)

                return result
        except Exception as exc:
            logger.warning("Spotify get_home failed: %s", exc)
            return []

    async def get_playlist_tracks(self, playlist_id: str) -> list[Track]:
        """Fetch playlist tracks via the partner API fetchPlaylist operation."""
        try:
            token = await self._auth.get_access_token()
            async with httpx.AsyncClient() as http:
                client_token = await self._get_client_token(http)
                op_hash = await self._get_partner_hash(http, "fetchPlaylist")
                if not op_hash:
                    logger.warning("Spotify: fetchPlaylist hash not found")
                    return []
                # Accept either a short playlist ID or a full spotify: URI
                pl_uri = (
                    playlist_id
                    if playlist_id.startswith("spotify:")
                    else f"spotify:playlist:{playlist_id}"
                )
                resp = await http.post(
                    _PARTNER_URL,
                    json={
                        "variables": {
                            "uri": pl_uri,
                            "offset": 0,
                            "limit": 100,
                            "enableWatchFeedEntrypoint": False,
                        },
                        "operationName": "fetchPlaylist",
                        "extensions": {"persistedQuery": {"version": 1, "sha256Hash": op_hash}},
                    },
                    headers=self._partner_headers(token, client_token),
                    timeout=15.0,
                )
                resp.raise_for_status()
                return self._parse_fetch_playlist(resp.json())
        except Exception as exc:
            logger.warning("Spotify get_playlist_tracks failed: %s", exc)
            return []

    async def get_library_playlists(self) -> list[Playlist]:
        """Return the user's library playlists via the partner API libraryV3 operation."""
        try:
            token = await self._auth.get_access_token()
            async with httpx.AsyncClient() as http:
                client_token = await self._get_client_token(http)
                op_hash = await self._get_partner_hash(http, "libraryV3")
                if not op_hash:
                    logger.warning("Spotify library: could not find 'libraryV3' operation hash")
                    return []
                resp = await http.post(
                    _PARTNER_URL,
                    json={
                        "variables": {
                            "filters": ["Playlists"],
                            "order": None,
                            "textFilter": "",
                            "features": ["LIKED_SONGS", "YOUR_EPISODES"],
                            "limit": 50,
                            "offset": 0,
                            "flatten": False,
                            "expandedFolders": [],
                            "folderUri": None,
                            "includeFoldersWhenFlattening": True,
                            "withCuration": False,
                        },
                        "operationName": "libraryV3",
                        "extensions": {
                            "persistedQuery": {"version": 1, "sha256Hash": op_hash}
                        },
                    },
                    headers=self._partner_headers(token, client_token),
                    timeout=15.0,
                )
                resp.raise_for_status()
                return self._parse_library_v3(resp.json())
        except Exception as exc:
            logger.warning("Spotify library fetch failed: %s", exc)
            return []

    # ── partner API response parsers ─────────────────────────────────────────

    @staticmethod
    def _extract_home_playlists(data: dict) -> list[tuple[str, str]]:
        """Return [(section_title, playlist_uri)] from the home response.

        Skips sections with no playlist items.
        """
        try:
            sections = data["data"]["home"]["sectionContainer"]["sections"]["items"]
        except (KeyError, TypeError):
            return []
        result: list[tuple[str, str]] = []
        for sec in sections:
            sec_data = sec.get("data") or {}
            title_raw = sec_data.get("title") or {}
            title = (
                title_raw.get("transformedLabel")
                or title_raw.get("text")
                or sec_data.get("name")
                or ""
            )
            items = (sec.get("sectionItems") or {}).get("items", [])
            for item in items:
                content = (item.get("content") or {}).get("data") or {}
                if content.get("__typename") == "Playlist":
                    uri = content.get("uri", "")
                    if uri:
                        result.append((title or "推荐", uri))
                        break
        return result

    @staticmethod
    def _parse_fetch_playlist(data: dict) -> list[Track]:
        """Parse the 'fetchPlaylist' partner API response.

        fetchPlaylist uses 'uri' instead of 'id' and 'trackDuration' instead
        of 'duration' — fields differ from the search response parsed by _to_track.
        """
        try:
            items = data["data"]["playlistV2"]["content"]["items"]
        except (KeyError, TypeError):
            return []
        tracks: list[Track] = []
        for item in items:
            item_data = (item.get("itemV2") or item).get("data") or {}
            if item_data.get("__typename") != "Track":
                continue
            try:
                uri = item_data.get("uri", "")
                track_id = (
                    item_data.get("id")
                    or (uri.rsplit(":", 1)[-1] if uri.startswith("spotify:track:") else "")
                )
                if not track_id:
                    continue
                artists_raw = item_data.get("artists") or {}
                artist_items = (
                    artists_raw.get("items", []) if isinstance(artists_raw, dict) else artists_raw
                )
                artists = [
                    (a.get("profile") or a).get("name", "") for a in artist_items
                ]
                artists = [a for a in artists if a]
                album = item_data.get("albumOfTrack") or {}
                sources = (album.get("coverArt") or {}).get("sources", [])
                cover = sources[0].get("url", "") if sources else ""
                dur = (
                    item_data.get("trackDuration")
                    or item_data.get("duration")
                    or {}
                )
                tracks.append(Track(
                    id=track_id, platform="spotify",
                    title=item_data.get("name", ""),
                    artist=artists[0] if artists else "",
                    artists=artists,
                    album=album.get("name", ""),
                    album_cover_url=cover,
                    duration_ms=dur.get("totalMilliseconds", 0),
                ))
            except Exception:
                continue
        return tracks

    @staticmethod
    def _parse_library_v3(data: dict) -> list[Playlist]:
        """Parse the 'libraryV3' partner API response.

        Handles both regular Playlists and PseudoPlaylist (Liked Songs).
        For special playlists the full URI is stored as the id so that
        get_playlist_tracks can pass it directly to fetchPlaylist.
        """
        try:
            items = data["data"]["me"]["libraryV3"]["items"]
        except (KeyError, TypeError):
            return []
        playlists: list[Playlist] = []
        for entry in items:
            try:
                content = (entry.get("item") or {}).get("data") or {}
                typename = content.get("__typename", "")
                if "playlist" not in typename.lower():
                    continue
                uri = content.get("uri", "")
                name = content.get("name", "")
                if not uri or not name:
                    continue
                # For regular playlists extract the short ID; for special ones keep full URI
                if uri.startswith("spotify:playlist:"):
                    pl_id = content.get("id") or uri.split("spotify:playlist:", 1)[1]
                else:
                    pl_id = uri  # e.g. "spotify:collection:tracks" (Liked Songs)
                image_items = (content.get("images") or {}).get("items", [])
                cover = ""
                if image_items:
                    sources = image_items[0].get("sources", [])
                    cover = sources[-1].get("url", "") if sources else ""
                track_count = (content.get("tracks") or {}).get("totalCount", 0)
                playlists.append(Playlist(
                    id=pl_id, platform="spotify", name=name,
                    cover_url=cover, track_count=track_count,
                ))
            except Exception:
                continue
        return playlists

    @staticmethod
    def _parse_search(data: dict) -> list[Track]:
        try:
            items = data["data"]["searchV2"]["tracksV2"]["items"]
        except (KeyError, TypeError):
            logger.warning("Unexpected Spotify search response shape")
            return []

        tracks: list[Track] = []
        for item in items:
            try:
                tracks.append(SpotifyClient._to_track(item["item"]["data"]))
            except (KeyError, TypeError, AttributeError):
                continue
        return tracks

    @staticmethod
    def _parse_webapi_search(data: dict) -> list[Track]:
        items = (data.get("tracks") or {}).get("items") or []
        return [SpotifyClient._to_webapi_track(item) for item in items if item]

    @staticmethod
    def _parse_search_suggestions(data: dict) -> list[Track]:
        raw_items = (
            data.get("data", {})
            .get("searchV2", {})
            .get("topResultsV2", {})
            .get("itemsV2", [])
        )
        tracks: list[Track] = []
        for raw in raw_items:
            wrapper = raw.get("item") or raw
            if wrapper.get("__typename") != "TrackResponseWrapper":
                continue
            track_data = wrapper.get("data") or wrapper.get("track") or {}
            if track_data:
                tracks.append(SpotifyClient._to_suggestion_track(track_data))
        return tracks

    @staticmethod
    def _to_track(data: dict) -> Track:
        artists = [
            artist["profile"]["name"]
            for artist in data.get("artists", {}).get("items", [])
            if artist.get("profile", {}).get("name")
        ]
        album = data.get("albumOfTrack", {}) or {}
        sources = album.get("coverArt", {}).get("sources", []) or []
        cover = sources[0].get("url", "") if sources else ""
        return Track(
            id=data.get("id", ""),
            platform="spotify",
            title=data.get("name", ""),
            artist=artists[0] if artists else "",
            artists=artists,
            album=album.get("name", ""),
            album_cover_url=cover,
            duration_ms=data.get("duration", {}).get("totalMilliseconds", 0),
            is_explicit=data.get("contentRating", {}).get("label", "") == "EXPLICIT",
        )

    @staticmethod
    def _to_webapi_track(data: dict) -> Track:
        artists = [artist.get("name", "") for artist in data.get("artists", []) if artist.get("name")]
        album = data.get("album") or {}
        images = album.get("images") or []
        cover = images[0].get("url", "") if images else ""
        duration_ms = data.get("duration_ms") or 0
        return Track(
            id=data.get("id", ""),
            platform="spotify",
            title=data.get("name", ""),
            artist=artists[0] if artists else "",
            artists=artists,
            album=album.get("name", ""),
            album_cover_url=cover,
            duration_ms=duration_ms,
            is_explicit=bool(data.get("explicit", False)),
        )

    @staticmethod
    def _to_suggestion_track(data: dict) -> Track:
        uri = data.get("uri", "")
        track_id = data.get("id") or uri.rsplit(":", 1)[-1]
        artists_raw = data.get("artists", {})
        if isinstance(artists_raw, dict):
            artist_items = artists_raw.get("items", [])
        else:
            artist_items = artists_raw or []
        artists = []
        for artist in artist_items:
            profile = artist.get("profile", {}) if isinstance(artist, dict) else {}
            name = profile.get("name") or artist.get("name", "")
            if name:
                artists.append(name)
        album = data.get("albumOfTrack") or data.get("album") or {}
        sources = (album.get("coverArt") or {}).get("sources") or album.get("images") or []
        cover = sources[0].get("url", "") if sources else ""
        duration = data.get("duration") or {}
        return Track(
            id=track_id,
            platform="spotify",
            title=data.get("name", ""),
            artist=artists[0] if artists else "",
            artists=artists,
            album=album.get("name", ""),
            album_cover_url=cover,
            duration_ms=duration.get("totalMilliseconds") or data.get("duration_ms") or 0,
            is_explicit=(data.get("contentRating") or {}).get("label") == "EXPLICIT",
        )

    @staticmethod
    def _to_playlist(data: dict) -> Playlist:
        images = data.get("images", []) or []
        cover = images[0].get("url", "") if images else ""
        return Playlist(
            id=data.get("id", ""),
            platform="spotify",
            name=data.get("name", ""),
            cover_url=cover,
            track_count=(data.get("tracks") or {}).get("total", 0),
        )


def _retry_after_seconds(resp: httpx.Response) -> int:
    try:
        return max(1, int(resp.headers.get("Retry-After", "30")))
    except ValueError:
        return 30
