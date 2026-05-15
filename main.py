from __future__ import annotations
import asyncio
import logging
import sys
from pathlib import Path
from PyQt6.QtWidgets import QApplication

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: F401 — must precede QApplication
from PyQt6.QtGui import QIcon, QImageReader, QPainter, QPixmap
from PyQt6.QtCore import Qt
import qasync
from core.app_controller import AppController
from ui.app_window import MainWindow


def _load_app_icon() -> QIcon:
    svg = Path(__file__).parent / "assets/icons/omnia-icon-pixel-cat-skyline-right-converge-meteors.svg"
    if not svg.exists():
        return QIcon()
    from PyQt6.QtSvg import QSvgRenderer
    renderer = QSvgRenderer(str(svg))
    icon = QIcon()
    for size in (32, 64, 128, 256, 512, 1024):
        px = QPixmap(size, size)
        px.fill(Qt.GlobalColor.transparent)
        p = QPainter(px)
        renderer.render(p)
        p.end()
        icon.addPixmap(px)
    return icon


async def _run(app: QApplication) -> None:
    ctrl = AppController()
    await ctrl.init()

    window = MainWindow(ctrl)
    volume = await ctrl.get_initial_volume()
    ctrl.set_volume(volume)

    window.show()

    # Sync stop on aboutToQuit — fires reliably even when quit() bypasses lastWindowClosed.
    app.aboutToQuit.connect(ctrl.stop_audio_sync)

    closed: asyncio.Future = asyncio.get_event_loop().create_future()
    app.lastWindowClosed.connect(
        lambda: closed.set_result(None) if not closed.done() else None
    )
    try:
        await closed
    finally:
        await ctrl.close()


def main() -> None:
    QImageReader.setAllocationLimit(1024)  # raise Qt 6 default 256 MB → 1 GB
    app = QApplication(sys.argv)
    app.setApplicationName("Omnia")
    app.setApplicationVersion("0.1.0")
    app.setWindowIcon(_load_app_icon())

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    with loop:
        loop.run_until_complete(_run(app))


if __name__ == "__main__":
    main()
