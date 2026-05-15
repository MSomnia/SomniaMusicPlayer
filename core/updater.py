"""Git-based auto-updater for SomniaMusicPlayer."""
from __future__ import annotations
import asyncio
import logging
import os
import sys
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Repo root is one directory above this file (core/)
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@dataclass
class UpdateStatus:
    available: bool
    local_commit: str = ""
    remote_commit: str = ""
    error: str = ""
    commit_messages: list[str] = field(default_factory=list)

    @property
    def local_short(self) -> str:
        return self.local_commit[:7] if self.local_commit else "unknown"

    @property
    def remote_short(self) -> str:
        return self.remote_commit[:7] if self.remote_commit else ""


async def _run(args: list[str]) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=_REPO_ROOT,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode, stdout.decode().strip(), stderr.decode().strip()


async def get_local_commit() -> str:
    code, out, _ = await _run(["git", "rev-parse", "HEAD"])
    return out if code == 0 else ""


async def fetch_origin() -> bool:
    code, _, err = await _run(["git", "fetch", "origin"])
    if code != 0:
        logger.warning("git fetch failed: %s", err)
    return code == 0


async def _get_upstream_commit() -> str:
    """Remote commit for current branch's upstream."""
    code, out, _ = await _run(["git", "rev-parse", "@{u}"])
    if code == 0 and out:
        return out
    # Fallback: origin/main
    code, out, _ = await _run(["git", "rev-parse", "origin/main"])
    return out if code == 0 else ""


async def _get_new_commit_messages(local: str, remote: str) -> list[str]:
    code, out, _ = await _run([
        "git", "log", "--oneline", f"{local}..{remote}"
    ])
    if code != 0 or not out:
        return []
    return out.splitlines()[:5]  # at most 5 lines


async def check_for_update() -> UpdateStatus:
    local = await get_local_commit()
    if not local:
        return UpdateStatus(available=False, error="无法读取本地版本")

    if not await fetch_origin():
        return UpdateStatus(available=False, local_commit=local, error="网络错误，无法连接到服务器")

    remote = await _get_upstream_commit()
    if not remote:
        return UpdateStatus(available=False, local_commit=local, error="无法获取远程版本")

    if remote == local:
        return UpdateStatus(available=False, local_commit=local, remote_commit=remote)

    messages = await _get_new_commit_messages(local, remote)
    return UpdateStatus(
        available=True,
        local_commit=local,
        remote_commit=remote,
        commit_messages=messages,
    )


async def apply_update() -> tuple[bool, str]:
    """Pull and rebase. Returns (success, message)."""
    code, out, err = await _run(["git", "pull", "--rebase"])
    if code == 0:
        return True, out or "更新成功"
    return False, err or out or "更新失败，请检查网络或手动更新"


def restart_app() -> None:
    """Replace current process with a fresh instance of the app."""
    logger.info("Restarting app for update...")
    os.execv(sys.executable, [sys.executable] + sys.argv)
