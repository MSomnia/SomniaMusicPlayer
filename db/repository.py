from __future__ import annotations
import aiosqlite
import hashlib
import json
import os
from pathlib import Path

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

# AES-256 key derived from a stable app secret (not user-facing)
_CRED_KEY = hashlib.pbkdf2_hmac(
    "sha256",
    b"SomniaMusicPlayer",
    b"netease-credential-salt",
    iterations=100_000,
    dklen=32,
)

DB_PATH = Path.home() / ".somniaplayer" / "app.db"
_SCHEMA = Path(__file__).parent / "schema.sql"

_DEFAULTS: dict[str, str] = {
    "volume":           "70",
    "repeat_mode":      "none",
    "shuffle":          "false",
    "cover_rotation":   "true",
    "lyrics_font_size": "22",
    "display_name":     "Somnia",
    "background_image_path": "",
}


class AppRepository:
    def __init__(self, db_path: Path = DB_PATH) -> None:
        self._path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._path)
        await self._db.executescript(_SCHEMA.read_text())
        for key, value in _DEFAULTS.items():
            await self._db.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
        await self._db.commit()

    async def get_setting(self, key: str) -> str | None:
        async with self._db.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None

    async def set_setting(self, key: str, value: str) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )
        await self._db.commit()

    async def save_credential(self, platform: str, data: dict) -> None:
        iv = os.urandom(16)
        cipher = AES.new(_CRED_KEY, AES.MODE_CBC, iv)
        plaintext = json.dumps(data).encode()
        blob = iv + cipher.encrypt(pad(plaintext, AES.block_size))
        import time
        await self._db.execute(
            "INSERT OR REPLACE INTO credentials (platform, data, updated_at) VALUES (?, ?, ?)",
            (platform, blob, int(time.time())),
        )
        await self._db.commit()

    async def load_credential(self, platform: str) -> dict | None:
        async with self._db.execute(
            "SELECT data FROM credentials WHERE platform = ?", (platform,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        blob: bytes = row[0]
        iv, ciphertext = blob[:16], blob[16:]
        cipher = AES.new(_CRED_KEY, AES.MODE_CBC, iv)
        plaintext = unpad(cipher.decrypt(ciphertext), AES.block_size)
        return json.loads(plaintext)

    async def delete_credential(self, platform: str) -> None:
        await self._db.execute(
            "DELETE FROM credentials WHERE platform = ?", (platform,)
        )
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None
