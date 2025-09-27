from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem
from PyQt6.QtCore import (
    Qt,
    QRectF,
    QPropertyAnimation,
    pyqtProperty,
    QPointF,
    QParallelAnimationGroup,
    QEasingCurve,
    QTimer
)
from PyQt6.QtGui import QPixmap, QTransform, QPainter, QCursor
import random

class ImageViewer(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.setStyleSheet("background-color: black;")
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setFrameShape(self.Shape.NoFrame)

        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        self.pixmap_item = QGraphicsPixmapItem()
        self.scene.addItem(self.pixmap_item)

        self._scale = 1.0
        self._center = QPointF(0, 0)
        self.base_scale = 1.0

        self.zoom_anim = None
        self.pan_anim = None
        self.anim_group = None

        # Disable scrollbars
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Enable mouse tracking for cursor hiding
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)

        # Setup auto-hide cursor timer
        self.cursor_timer = QTimer(self)
        self.cursor_timer.setInterval(5000)  # 5 seconds
        self.cursor_timer.timeout.connect(self.hide_cursor)
        self.cursor_timer.start()

        # Force initial cursor
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseMoveEvent(self, event):
        if self.cursor().shape() != Qt.CursorShape.ArrowCursor:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        self.cursor_timer.start()  # Reset the timer
        super().mouseMoveEvent(event)

    def hide_cursor(self):
        self.setCursor(Qt.CursorShape.BlankCursor)

    def show_image(self, image_path, duration=5000, motion=True):
        # Stop previous animation if running
        if self.anim_group and self.anim_group.state() == self.anim_group.State.Running:
            self.anim_group.stop()
            self.anim_group.deleteLater()
            self.anim_group = None

        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            return

        self.pixmap_item.setPixmap(pixmap)
        self.scene.setSceneRect(QRectF(pixmap.rect()))
        self.resetTransform()
        self._scale = 1.0
        self.set_center(self.sceneRect().center())

        # Calculate base scale so image fits screen
        self.base_scale = self.calculate_fit_scale(pixmap)

        if motion:
            self.start_zoom_and_pan(duration)
        else:
            self.set_scale(self.base_scale)
            self.centerOn(self.sceneRect().center())

    def calculate_fit_scale(self, pixmap):
        if pixmap.isNull():
            return 1.0

        view_size = self.viewport().size()
        pixmap_size = pixmap.size()

        if pixmap_size.width() == 0 or pixmap_size.height() == 0:
            return 1.0

        scale_x = view_size.width() / pixmap_size.width()
        scale_y = view_size.height() / pixmap_size.height()
        return min(scale_x, scale_y)

    def get_scale(self):
        return self._scale

    def set_scale(self, scale):
        self._scale = scale
        transform = QTransform()
        transform.scale(scale, scale)
        self.setTransform(transform)

    scale = pyqtProperty(float, fget=get_scale, fset=set_scale)

    def get_center(self):
        return self._center

    def set_center(self, point):
        self._center = point
        self.centerOn(point)

    center = pyqtProperty(QPointF, fget=get_center, fset=set_center)

    def start_zoom_and_pan(self, duration=5000):
        # Stop any previous animation safely
        if self.anim_group and self.anim_group.state() == self.anim_group.State.Running:
            self.anim_group.stop()
            self.anim_group.deleteLater()
            self.anim_group = None

        # Random zoom direction
        zoom_factor = 1.05 if random.choice([True, False]) else 0.95
        start_scale = self.base_scale
        end_scale = self.base_scale * zoom_factor

        self.set_scale(start_scale)

        self.zoom_anim = QPropertyAnimation(self, b"scale")
        self.zoom_anim.setDuration(duration)
        self.zoom_anim.setStartValue(start_scale)
        self.zoom_anim.setEndValue(end_scale)
        self.zoom_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

        # Pan animation
        scene_rect = self.sceneRect()
        start_point = self.get_random_edge_point(scene_rect)
        end_point = self.get_random_edge_point(scene_rect)

        self.set_center(start_point)

        self.pan_anim = QPropertyAnimation(self, b"center")
        self.pan_anim.setDuration(duration)
        self.pan_anim.setStartValue(start_point)
        self.pan_anim.setEndValue(end_point)
        self.pan_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

        self.anim_group = QParallelAnimationGroup()
        self.anim_group.addAnimation(self.zoom_anim)
        self.anim_group.addAnimation(self.pan_anim)
        self.anim_group.start()

    def get_random_edge_point(self, rect: QRectF):
        options = [
            rect.topLeft(),
            rect.topRight(),
            rect.bottomLeft(),
            rect.bottomRight(),
            QPointF(rect.center().x(), rect.top()),
            QPointF(rect.center().x(), rect.bottom()),
            QPointF(rect.left(), rect.center().y()),
            QPointF(rect.right(), rect.center().y()),
            rect.center(),
        ]
        return random.choice(options)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Do not use fitInView, manual scaling is handled elsewhere
