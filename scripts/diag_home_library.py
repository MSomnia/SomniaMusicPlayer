"""Diagnostic script: test get_home() and get_library_playlists() for Spotify and YTMusic.

Run from the project root:
    python3 scripts/diag_home_library.py
"""
from __future__ import annotations
import asyncio
import logging
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")


async def _test_spotify() -> None:
    from db.repository import AppRepository
    from platforms.spotify.auth import SpotifyAuth
    from platforms.spotify.client import SpotifyClient
    import httpx

    repo = AppRepository()
    await repo.init()
    auth = SpotifyAuth(repo)
    sp_dc = await auth.load_sp_dc()
    print(f"\n[Spotify] sp_dc present: {bool(sp_dc)}")
    if not sp_dc:
        print("[Spotify] Not authenticated — skip")
        await repo.close()
        return

    try:
        token = await auth.get_access_token()
        print(f"[Spotify] access token: {token[:20]}...")
    except Exception as exc:
        print(f"[Spotify] get_access_token FAILED: {exc}")
        await repo.close()
        return

    client = SpotifyClient(auth)

    # --- get_home: recently-played ---
    print("\n[Spotify] Testing recently-played endpoint...")
    try:
        async with httpx.AsyncClient() as http:
            resp = await http.get(
                "https://api.spotify.com/v1/me/player/recently-played",
                params={"limit": 5},
                headers={
                    "Authorization": f"Bearer {token}",
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
                    ),
                    "App-Platform": "WebPlayer",
                    "Spotify-App-Version": "1.2.50.248",
                },
                timeout=10.0,
            )
        print(f"  Status: {resp.status_code}")
        print(f"  Response (first 500 chars): {resp.text[:500]}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"  items count: {len(data.get('items', []))}")
    except Exception as exc:
        print(f"  EXCEPTION: {exc}")
        traceback.print_exc()

    # --- get_home via client ---
    print("\n[Spotify] Testing client.get_home()...")
    try:
        sections = await client.get_home()
        print(f"  sections count: {len(sections)}")
        for title, tracks in sections:
            print(f"    [{title}] {len(tracks)} tracks")
            if tracks:
                t = tracks[0]
                print(f"      first: id={t.id!r} title={t.title!r} artist={t.artist!r}")
    except Exception as exc:
        print(f"  EXCEPTION: {exc}")
        traceback.print_exc()

    # --- get_library_playlists ---
    print("\n[Spotify] Testing /v1/me/playlists endpoint...")
    try:
        async with httpx.AsyncClient() as http:
            resp = await http.get(
                "https://api.spotify.com/v1/me/playlists",
                params={"limit": 5},
                headers={
                    "Authorization": f"Bearer {token}",
                    "App-Platform": "WebPlayer",
                    "Spotify-App-Version": "1.2.50.248",
                },
                timeout=10.0,
            )
        print(f"  Status: {resp.status_code}")
        print(f"  Response (first 500 chars): {resp.text[:500]}")
    except Exception as exc:
        print(f"  EXCEPTION: {exc}")
        traceback.print_exc()

    print("\n[Spotify] Testing client.get_library_playlists()...")
    try:
        playlists = await client.get_library_playlists()
        print(f"  playlists count: {len(playlists)}")
        for pl in playlists[:3]:
            print(f"    id={pl.id!r} name={pl.name!r} count={pl.track_count!r}")
    except Exception as exc:
        print(f"  EXCEPTION: {exc}")
        traceback.print_exc()

    await repo.close()


async def _test_ytmusic() -> None:
    from db.repository import AppRepository
    from platforms.ytmusic.auth import YTMusicAuth
    from platforms.ytmusic.client import YTMusicClient

    repo = AppRepository()
    await repo.init()
    auth = YTMusicAuth(repo)
    headers = await auth.load_auth()
    print(f"\n[YTMusic] headers present: {bool(headers)}")
    if not headers:
        print("[YTMusic] Not authenticated — skip")
        await repo.close()
        return

    print(f"  header keys: {list(headers.keys())}")
    cookie_preview = headers.get("Cookie", "")[:80]
    print(f"  Cookie (first 80): {cookie_preview}")
    auth_header = headers.get("Authorization", "")[:60]
    print(f"  Authorization (first 60): {auth_header}")

    try:
        client = YTMusicClient(headers)
    except Exception as exc:
        print(f"[YTMusic] YTMusicClient init FAILED: {exc}")
        traceback.print_exc()
        await repo.close()
        return

    # --- get_home ---
    print("\n[YTMusic] Testing ytmusicapi.get_home()...")
    try:
        loop = asyncio.get_event_loop()
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=1) as ex:
            raw_home = await loop.run_in_executor(ex, client._ytm.get_home)
        print(f"  sections returned: {len(raw_home or [])}")
        for sec in (raw_home or [])[:4]:
            title = sec.get("title", "?")
            contents = sec.get("contents", [])
            n_with_vid = sum(1 for item in contents if item.get("videoId"))
            print(f"    [{title}] {len(contents)} items, {n_with_vid} have videoId")
            if contents:
                first = contents[0]
                print(f"      first item keys: {list(first.keys())}")
    except Exception as exc:
        print(f"  EXCEPTION: {exc}")
        traceback.print_exc()

    print("\n[YTMusic] Testing client.get_home()...")
    try:
        sections = await client.get_home()
        print(f"  processed sections: {len(sections)}")
        for title, tracks in sections:
            print(f"    [{title}] {len(tracks)} tracks")
    except Exception as exc:
        print(f"  EXCEPTION: {exc}")
        traceback.print_exc()

    # --- get_library_playlists ---
    print("\n[YTMusic] Testing ytmusicapi.get_library_playlists()...")
    try:
        loop = asyncio.get_event_loop()
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=1) as ex:
            raw_lib = await loop.run_in_executor(ex, client._ytm.get_library_playlists)
        print(f"  raw playlists: {len(raw_lib or [])}")
        for pl in (raw_lib or [])[:3]:
            print(f"    keys: {list(pl.keys())}")
            print(f"    id={pl.get('playlistId')!r} name={pl.get('title')!r} count={pl.get('count')!r}")
    except Exception as exc:
        print(f"  EXCEPTION: {exc}")
        traceback.print_exc()

    print("\n[YTMusic] Testing client.get_library_playlists()...")
    try:
        playlists = await client.get_library_playlists()
        print(f"  processed playlists: {len(playlists)}")
        for pl in playlists[:3]:
            print(f"    id={pl.id!r} name={pl.name!r} count={pl.track_count!r}")
    except Exception as exc:
        print(f"  EXCEPTION: {exc}")
        traceback.print_exc()

    # --- get_playlist_tracks for first playlist ---
    print("\n[YTMusic] Testing get_playlist_tracks for first playlist...")
    try:
        raw_lib2 = await asyncio.get_event_loop().run_in_executor(
            None, client._ytm.get_library_playlists
        )
        if raw_lib2:
            first_id = raw_lib2[0].get("playlistId", "")
            print(f"  Testing playlist id={first_id!r}")
            tracks = await client.get_playlist_tracks(first_id)
            print(f"  tracks count: {len(tracks)}")
            if tracks:
                t = tracks[0]
                print(f"    first: id={t.id!r} title={t.title!r}")
    except Exception as exc:
        print(f"  EXCEPTION: {exc}")
        traceback.print_exc()

    await repo.close()


async def main() -> None:
    print("=" * 60)
    print("SomniaMusicPlayer — Home & Library Diagnostic")
    print("=" * 60)
    await _test_spotify()
    await _test_ytmusic()
    print("\nDiagnostic complete.")


if __name__ == "__main__":
    asyncio.run(main())
