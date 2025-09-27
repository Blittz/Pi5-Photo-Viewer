import random
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QRectF, QPointF
from PyQt6.QtGui import QPixmap, QTransform, QPainter
from PyQt6.QtWidgets import (
    QGraphicsView,
    QGraphicsScene,
    QGraphicsPixmapItem,
    QSizePolicy,
)


class ImageViewer(QGraphicsView):
    def __init__(self, motion_enabled=True):
        super().__init__()

        self.motion_enabled = motion_enabled
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        self.pixmap_item = QGraphicsPixmapItem()
        self.scene.addItem(self.pixmap_item)

        self.setRenderHints(self.renderHints() | QPainter.RenderHint.SmoothPixmapTransform)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)

        self.motion_timer = QTimer(self)
        self.motion_timer.setSingleShot(True)
        self.motion_timer.timeout.connect(self.start_motion)

        self.motion_duration = 5000  # default duration (ms), can be overridden per image
        self._current_pixmap = QPixmap()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._current_pixmap.isNull():
            self._fit_pixmap()

    def set_image(self, image_path, duration=None):
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            return

        self._current_pixmap = pixmap
        self.pixmap_item.setPixmap(pixmap)

        self.scene.setSceneRect(QRectF(pixmap.rect()))
        self.resetTransform()
        self._fit_pixmap()

        if duration:
            self.motion_duration = duration * 1000

        if self.motion_enabled:
            self.motion_timer.start(50)  # slight delay to allow layout

    def start_motion(self):
        if not self.motion_enabled:
            return

        self.resetTransform()
        self._fit_pixmap()

        start_scale = 1.0
        end_scale = 1.1

        direction = random.choice(['up', 'down', 'left', 'right', 'diag'])

        dx = dy = 0
        pan_amount = 50

        if direction == 'up':
            dy = -pan_amount
        elif direction == 'down':
            dy = pan_amount
        elif direction == 'left':
            dx = -pan_amount
        elif direction == 'right':
            dx = pan_amount
        elif direction == 'diag':
            dx = dy = pan_amount

        steps = 100
        interval = self.motion_duration // steps
        self.step = 0
        self.steps = steps
        self.dx = dx / steps
        self.dy = dy / steps
        self.scale_step = (end_scale - start_scale) / steps
        self.current_scale = start_scale

        self.motion_anim_timer = QTimer(self)
        self.motion_anim_timer.timeout.connect(self.apply_motion_step)
        self.motion_anim_timer.start(interval)

    def apply_motion_step(self):
        if self.step >= self.steps:
            self.motion_anim_timer.stop()
            return

        self.current_scale += self.scale_step
        transform = QTransform()
        transform.translate(self.dx * self.step, self.dy * self.step)
        transform.scale(self.current_scale, self.current_scale)

        self.setTransform(transform)
        self.step += 1

    def _fit_pixmap(self):
        """Scale the current image so it fits the available viewport."""
        if self.pixmap_item.pixmap().isNull():
            return

        self.fitInView(self.pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
