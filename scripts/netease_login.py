import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PyQt6.QtWidgets import QApplication
import qasync
from db.repository import AppRepository
from platforms.netease.auth import NeteaseAuth


async def main():
    repo = AppRepository()
    await repo.init()

    auth = NeteaseAuth(repo)
    # 先看看本地有没有已保存的 Cookie
    existing = await auth.load_cookies()
    if existing:
        print(f"已有保存的登录态：MUSIC_U = {existing['MUSIC_U'][:20]}...")
    else:
        print("未找到登录态，打开浏览器登录窗口...")
        cookies = await auth.login()
        if cookies:
            print(f"登录成功！MUSIC_U = {cookies['MUSIC_U'][:20]}...")
        else:
            print("取消登录")

    await repo.close()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    with loop:
        loop.run_until_complete(main())
