from __future__ import annotations

from PyQt6.QtCore import QPoint, QRect, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import (
    QGraphicsBlurEffect, QGraphicsPixmapItem, QGraphicsScene, QWidget,
)

from ui.theme import COLORS


def paint_frosted_panel(widget: QWidget, painter: QPainter, radius: int = 8) -> None:
    path = QPainterPath()
    path.addRoundedRect(widget.rect().toRectF(), radius, radius)

    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setClipPath(path)

    root = widget.window().centralWidget() if widget.window() else None
    background = _root_background(root)
    if background.isNull() or root is None:
        painter.fillPath(path, QColor(COLORS["bg_panel"]))
    else:
        panel = _panel_background_sample(widget, root, background)
        painter.drawPixmap(0, 0, _soft_blur(panel))
        painter.fillPath(path, QColor(34, 34, 34, 190))

    painter.setClipping(False)
    painter.setPen(QColor(255, 255, 255, 22))
    painter.drawPath(path)


def _root_background(root: QWidget | None) -> QPixmap:
    if root is None:
        return QPixmap()
    getter = getattr(root, "background_pixmap", None)
    if getter is None:
        return QPixmap()
    return getter()


def _panel_background_sample(
    widget: QWidget,
    root: QWidget,
    background: QPixmap,
) -> QPixmap:
    scaled = background.scaled(
        root.size(),
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    root_offset = QPoint(
        (root.width() - scaled.width()) // 2,
        (root.height() - scaled.height()) // 2,
    )
    panel_pos = widget.mapTo(root, QPoint(0, 0))
    source_rect = QRect(
        panel_pos.x() - root_offset.x(),
        panel_pos.y() - root_offset.y(),
        widget.width(),
        widget.height(),
    )
    return scaled.copy(source_rect)


def _soft_blur(pixmap: QPixmap) -> QPixmap:
    if pixmap.isNull():
        return pixmap

    scene = QGraphicsScene()
    item = QGraphicsPixmapItem(pixmap)
    blur = QGraphicsBlurEffect()
    blur.setBlurRadius(22)
    blur.setBlurHints(QGraphicsBlurEffect.BlurHint.QualityHint)
    item.setGraphicsEffect(blur)
    scene.addItem(item)
    scene.setSceneRect(QRectF(pixmap.rect()))

    result = QPixmap(pixmap.size())
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    scene.render(painter, QRectF(result.rect()), QRectF(pixmap.rect()))
    painter.end()
    return result
