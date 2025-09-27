import math
import random
<<<<<<< ours
from PyQt6.QtCore import Qt, QTimer, QRectF, QVariantAnimation
=======
from PyQt6.QtCore import Qt, QTimer, QRectF, QVariantAnimation, QEasingCurve
>>>>>>> theirs
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

        self.motion_anim = QVariantAnimation(self)
<<<<<<< ours
=======
        self.motion_anim.setEasingCurve(QEasingCurve.Type.Linear)
>>>>>>> theirs
        self.motion_anim.valueChanged.connect(self.apply_motion_progress)

        self.motion_duration = 5000  # default duration (ms), can be overridden per image
        self._current_pixmap = QPixmap()
        self.base_transform = QTransform()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._current_pixmap.isNull():
            self._fit_pixmap()

    def set_image(self, image_path, duration=None):
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            return

        self.motion_timer.stop()
        self.motion_anim.stop()

        self._current_pixmap = pixmap
        self.pixmap_item.setPixmap(pixmap)

        self.scene.setSceneRect(QRectF(pixmap.rect()))
        self.resetTransform()
        self._fit_pixmap()

        if duration is not None:
            self.motion_duration = max(0, int(duration * 1000))

        if self.motion_enabled:
            self.motion_timer.start(50)  # slight delay to allow layout

    def start_motion(self):
        if not self.motion_enabled:
            return

        self.resetTransform()
        self._fit_pixmap()

        self.base_transform = self.transform()

        zoom_in = random.choice([True, False])
        if zoom_in:
            self.start_scale = 1.0
            self.end_scale = random.uniform(1.08, 1.2)
        else:
            self.start_scale = random.uniform(1.08, 1.2)
            self.end_scale = 1.0

        pan_ratio = random.uniform(0.02, 0.08)
        pan_angle = random.uniform(0, 2 * math.pi)
        pixmap_rect = self.pixmap_item.boundingRect()
<<<<<<< ours
<<<<<<< ours
        total_dx = total_dy = 0.0

        if direction == 'left':
            total_dx = -pixmap_rect.width() * pan_ratio
        elif direction == 'right':
            total_dx = pixmap_rect.width() * pan_ratio
        elif direction == 'diag':
            total_dx = pixmap_rect.width() * pan_ratio * random.choice([-1, 1])

        if direction == 'up':
            total_dy = -pixmap_rect.height() * pan_ratio
        elif direction == 'down':
            total_dy = pixmap_rect.height() * pan_ratio
        elif direction == 'diag':
            total_dy = pixmap_rect.height() * pan_ratio * random.choice([-1, 1])

        self.total_dx = total_dx
        self.total_dy = total_dy

        if self.motion_duration <= 0:
            return

        self.motion_anim.stop()
        self.motion_anim.setStartValue(0.0)
        self.motion_anim.setEndValue(1.0)
        self.motion_anim.setDuration(self.motion_duration)
        self.motion_anim.start()

    def apply_motion_progress(self, progress):
        progress = max(0.0, min(1.0, float(progress)))

=======
=======
>>>>>>> theirs

        self.total_dx = pixmap_rect.width() * pan_ratio * math.cos(pan_angle)
        self.total_dy = pixmap_rect.height() * pan_ratio * math.sin(pan_angle)

        if self.motion_duration <= 0:
            return

        self.motion_anim.stop()
        self.motion_anim.setStartValue(0.0)
        self.motion_anim.setEndValue(1.0)
        self.motion_anim.setDuration(self.motion_duration)
        self.apply_motion_progress(0.0)
        self.motion_anim.start()

    def apply_motion_progress(self, progress):
        progress = max(0.0, min(1.0, float(progress)))

<<<<<<< ours
>>>>>>> theirs
=======
>>>>>>> theirs
        current_scale = self.start_scale + (self.end_scale - self.start_scale) * progress
        current_dx = self.total_dx * progress
        current_dy = self.total_dy * progress

        transform = QTransform(self.base_transform)
        transform.scale(current_scale, current_scale)
        transform.translate(current_dx, current_dy)

        self.setTransform(transform)

    def _fit_pixmap(self):
        """Scale the current image so it fits the available viewport."""
        if self.pixmap_item.pixmap().isNull():
            return

        self.fitInView(self.pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
        self.base_transform = self.transform()
