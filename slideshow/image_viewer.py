import math
import random
import os

from PyQt6.QtCore import Qt, QTimer, QRectF, QVariantAnimation, QEasingCurve
from PyQt6.QtGui import QPixmap, QTransform, QPainter
from PyQt6.QtWidgets import (
    QGraphicsView,
    QGraphicsScene,
    QGraphicsPixmapItem,
    QSizePolicy,
    QLabel,
)


class ImageViewer(QGraphicsView):
    def __init__(self, motion_enabled=True, overlay_percentage=40):
        super().__init__()

        self.motion_enabled = motion_enabled
        self.overlay_percentage = float(overlay_percentage)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setBackgroundBrush(Qt.GlobalColor.black)
        self.scene.setBackgroundBrush(Qt.GlobalColor.black)

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
        self.motion_anim.setEasingCurve(QEasingCurve.Type.Linear)
        self.motion_anim.valueChanged.connect(self.apply_motion_progress)

        self.motion_duration = 5000  # default duration (ms), can be overridden per image
        self._current_pixmap = QPixmap()
        self.base_transform = QTransform()
        self.start_scale = 1.0
        self.end_scale = 1.0
        self.total_dx = 0.0
        self.total_dy = 0.0
        self.motion_prepared = False

        self.overlay_label = QLabel(self)
        self.overlay_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.overlay_label.setStyleSheet(
            "color: white; background-color: rgba(0, 0, 0, 180);"
            "padding: 6px 14px; border-radius: 12px;"
        )
        self.overlay_label.setWordWrap(True)
        self.overlay_label.setVisible(False)
        self.overlay_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.overlay_margin = 20

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._current_pixmap.isNull():
            self._fit_pixmap()
        self._update_overlay_position()

    def set_image(self, image_path, duration=None):
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            self.overlay_label.setVisible(False)
            return

        self.motion_timer.stop()
        self.motion_anim.stop()

        self._current_pixmap = pixmap
        self.pixmap_item.setPixmap(pixmap)

        self.scene.setSceneRect(QRectF(pixmap.rect()))
        self.resetTransform()
        self._fit_pixmap()

        folder_name = os.path.basename(os.path.dirname(image_path))
        file_name = os.path.basename(image_path)
        overlay_text = f"{folder_name}\n{file_name}" if folder_name else file_name
        self.overlay_label.setText(overlay_text)
        self.overlay_label.setVisible(True)
        self.overlay_label.adjustSize()
        self.overlay_label.raise_()
        self._update_overlay_position()

        if self.motion_enabled:
            self._prepare_motion_parameters()
        else:
            self.motion_prepared = False

        if duration is not None:
            self.motion_duration = max(0, int(duration * 1000))

        if self.motion_enabled:
            self.motion_timer.start(50)  # slight delay to allow layout

    def start_motion(self):
        if not self.motion_enabled:
            return

        if self._current_pixmap.isNull():
            return

        if self.motion_duration <= 0:
            return

        self.setUpdatesEnabled(False)
        try:
            self.resetTransform()
            self._fit_pixmap()
            if self.motion_prepared:
                self.apply_motion_progress(0.0)
            else:
                self._prepare_motion_parameters()
        finally:
            self.setUpdatesEnabled(True)

        self.viewport().update()

        self.motion_anim.stop()
        self.motion_anim.setStartValue(0.0)
        self.motion_anim.setEndValue(1.0)
        self.motion_anim.setDuration(self.motion_duration)
        self.apply_motion_progress(0.0)
        self.motion_anim.start()

    def apply_motion_progress(self, progress):
        progress = max(0.0, min(1.0, float(progress)))

        current_scale = self.start_scale + (self.end_scale - self.start_scale) * progress
        current_dx = self.total_dx * progress
        current_dy = self.total_dy * progress

        transform = QTransform(self.base_transform)
        transform.scale(current_scale, current_scale)
        transform.translate(current_dx, current_dy)

        self.setTransform(transform)
        self._update_overlay_position()

    def _fit_pixmap(self):
        """Scale the current image so it fits the available viewport."""
        if self.pixmap_item.pixmap().isNull():
            return

        self.fitInView(self.pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
        self.base_transform = self.transform()

    def _prepare_motion_parameters(self):
        pixmap = self.pixmap_item.pixmap()
        if pixmap.isNull():
            self.motion_prepared = False
            return

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

        self.total_dx = pixmap_rect.width() * pan_ratio * math.cos(pan_angle)
        self.total_dy = pixmap_rect.height() * pan_ratio * math.sin(pan_angle)
        self.motion_prepared = True

        self.apply_motion_progress(0.0)

    def set_overlay_percentage(self, percentage):
        try:
            self.overlay_percentage = max(0.0, float(percentage))
        except (TypeError, ValueError):
            return
        self._update_overlay_position()

    def _update_overlay_position(self):
        max_width = self._calculate_overlay_max_width()
        if max_width <= 0 or self.overlay_label.text() == "":
            self.overlay_label.setVisible(False)
            return

<<<<<<< ours
        max_width = self._calculate_overlay_max_width()
        self.overlay_label.setMaximumWidth(max_width)
=======
        if not self.overlay_label.isVisible():
            self.overlay_label.setVisible(True)

        self.overlay_label.setFixedWidth(max_width)
>>>>>>> theirs
        self.overlay_label.adjustSize()
        # Enforce the computed width in case adjustSize shrinks it.
        if self.overlay_label.width() != max_width:
            self.overlay_label.resize(max_width, self.overlay_label.height())

        label_width = self.overlay_label.width()
        label_height = self.overlay_label.height()

        x = max(self.overlay_margin, (self.viewport().width() - label_width) // 2)
        y = self.viewport().height() - label_height - self.overlay_margin

        # Position relative to the widget coordinates.
        self.overlay_label.move(int(x), int(y))

    def _calculate_overlay_max_width(self):
<<<<<<< ours
        if self.overlay_percentage <= 0:
            return 0

=======
>>>>>>> theirs
        image_rect = self._get_displayed_pixmap_rect()
        if image_rect.isNull():
            return 0

        image_width = image_rect.width()
        max_width_by_image = int(image_width * (self.overlay_percentage / 100.0))

        viewport_limit = max(0, self.viewport().width() - self.overlay_margin * 2)
        if viewport_limit <= 0:
            return max(0, max_width_by_image)

        return max(0, min(max_width_by_image, viewport_limit))

    def _get_displayed_pixmap_rect(self):
        if self.pixmap_item.pixmap().isNull():
            return QRectF()

        transform = self.transform()
        return transform.mapRect(self.pixmap_item.boundingRect())
