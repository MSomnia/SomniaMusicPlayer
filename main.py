from __future__ import annotations
import asyncio
import sys
from PyQt6.QtWidgets import QApplication
import qasync
from ui.app_window import MainWindow
from db.repository import AppRepository


async def _run(app: QApplication) -> None:
    repo = AppRepository()
    await repo.init()

    window = MainWindow()

    volume_str = await repo.get_setting("volume")
    if volume_str:
        window.now_playing.set_volume(int(volume_str))

    window.show()

    window.now_playing.volume_changed.connect(
        lambda v: asyncio.ensure_future(repo.set_setting("volume", str(v)))
    )

    closed: asyncio.Future = asyncio.get_event_loop().create_future()
    app.lastWindowClosed.connect(
        lambda: closed.set_result(None) if not closed.done() else None
    )
    try:
        await closed
    finally:
        await repo.close()


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("SomniaMusicPlayer")
    app.setApplicationVersion("0.1.0")

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    with loop:
        loop.run_until_complete(_run(app))


if __name__ == "__main__":
    main()
