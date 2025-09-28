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
    def __init__(self, motion_enabled=True, title_font_size=24):
        super().__init__()

        self.motion_enabled = motion_enabled
        self.title_font_size = self._sanitize_font_size(title_font_size)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setBackgroundBrush(Qt.GlobalColor.black)
        self.scene.setBackgroundBrush(Qt.GlobalColor.black)

        self.pixmap_item = QGraphicsPixmapItem()
        self.pixmap_item.setTransformationMode(
            Qt.TransformationMode.SmoothTransformation
        )
        self.scene.addItem(self.pixmap_item)

        self.transition_item = QGraphicsPixmapItem()
        self.transition_item.setTransformationMode(
            Qt.TransformationMode.SmoothTransformation
        )
        self.transition_item.setVisible(False)
        self.scene.addItem(self.transition_item)

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

        self.transition_anim = QVariantAnimation(self)
        self.transition_anim.valueChanged.connect(self._apply_transition_progress)
        self.transition_anim.finished.connect(self._finalize_transition)
        self.transition_anim.setDuration(600)
        self.active_transition = None

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

    def set_image(self, image_path, duration=None, transition=None):
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            self.overlay_label.setVisible(False)
            return

        self.motion_timer.stop()
        self.motion_anim.stop()
        self.transition_anim.stop()
        if self.active_transition is not None:
            self._finalize_transition()

        has_previous = not self.pixmap_item.pixmap().isNull()
        previous_pixmap = self.pixmap_item.pixmap() if has_previous else QPixmap()

        if has_previous and not previous_pixmap.isNull():
            self.transition_item.setPixmap(previous_pixmap)
            self.transition_item.setVisible(True)
            self.transition_item.setOpacity(1.0)
            self.transition_item.setScale(1.0)
            self.transition_item.setPos(0.0, 0.0)
            self.transition_item.setTransformOriginPoint(
                self.transition_item.boundingRect().center()
            )
        else:
            self.transition_item.setVisible(False)

        self._current_pixmap = pixmap
        self.pixmap_item.setPixmap(pixmap)
        self.pixmap_item.setOpacity(1.0)
        self.pixmap_item.setScale(1.0)
        self.pixmap_item.setPos(0.0, 0.0)
        self.pixmap_item.setTransformOriginPoint(
            self.pixmap_item.boundingRect().center()
        )
        self.pixmap_item.setZValue(1)
        self.transition_item.setZValue(0)

        self.scene.setSceneRect(QRectF(pixmap.rect()))
        self.resetTransform()
        self._fit_pixmap()

        folder_name = os.path.basename(os.path.dirname(image_path))
        file_name = os.path.basename(image_path)
        overlay_text = f"{folder_name}\n{file_name}" if folder_name else file_name
        self.overlay_label.setText(overlay_text)
        self.overlay_label.setVisible(True)
        self.overlay_label.raise_()
        self._update_overlay_position()

        if self.motion_enabled:
            self._prepare_motion_parameters()
        else:
            self.motion_prepared = False

        if duration is not None:
            self.motion_duration = max(0, int(duration * 1000))

        transition_type = None
        if transition and has_previous:
            if isinstance(transition, str):
                lowered = transition.lower()
                if lowered in {"crossfade", "slide", "zoom"}:
                    transition_type = lowered
        if transition_type:
            self._start_transition(transition_type)
        else:
            self.transition_item.setVisible(False)
            self.pixmap_item.setOpacity(1.0)
            self.pixmap_item.setScale(1.0)
            self.pixmap_item.setPos(0.0, 0.0)

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

    def _start_transition(self, transition_type):
        self.active_transition = transition_type
        self.transition_item.setVisible(True)
        self.transition_anim.stop()
        self.transition_anim.setStartValue(0.0)
        self.transition_anim.setEndValue(1.0)

        if transition_type == "slide":
            width = self.scene.sceneRect().width()
            self.pixmap_item.setPos(width, 0.0)
            self.transition_item.setPos(0.0, 0.0)
            self.pixmap_item.setOpacity(1.0)
            self.transition_item.setOpacity(1.0)
        elif transition_type == "zoom":
            self.pixmap_item.setScale(0.85)
            self.pixmap_item.setOpacity(0.0)
            self.transition_item.setOpacity(1.0)
        else:
            self.active_transition = "crossfade"
            self.pixmap_item.setOpacity(0.0)
            self.transition_item.setOpacity(1.0)
            self.transition_item.setPos(0.0, 0.0)

        self._apply_transition_progress(0.0)
        self.transition_anim.start()

    def _apply_transition_progress(self, progress):
        if self.active_transition is None:
            return

        progress = max(0.0, min(1.0, float(progress)))

        if self.active_transition == "slide":
            width = self.scene.sceneRect().width()
            self.pixmap_item.setPos(width * (1.0 - progress), 0.0)
            self.transition_item.setPos(-width * progress, 0.0)
            self.transition_item.setOpacity(1.0 - progress)
        elif self.active_transition == "zoom":
            start_scale = 0.85
            end_scale = 1.0
            current_scale = start_scale + (end_scale - start_scale) * progress
            self.pixmap_item.setScale(current_scale)
            self.pixmap_item.setOpacity(progress)
            self.transition_item.setOpacity(1.0 - progress)
        else:  # crossfade
            self.pixmap_item.setOpacity(progress)
            self.transition_item.setOpacity(1.0 - progress)

        self._update_overlay_position()

    def _finalize_transition(self):
        self.pixmap_item.setPos(0.0, 0.0)
        self.pixmap_item.setScale(1.0)
        self.pixmap_item.setOpacity(1.0)
        self.transition_item.setVisible(False)
        self.transition_item.setOpacity(1.0)
        self.transition_item.setScale(1.0)
        self.transition_item.setPos(0.0, 0.0)
        self.active_transition = None
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

    def set_title_font_size(self, font_size):
        sanitized = self._sanitize_font_size(font_size)
        if math.isclose(self.title_font_size, sanitized):
            return
        self.title_font_size = sanitized
        self._update_overlay_position()

    def _update_overlay_position(self):
        if self.overlay_label.text() == "":
            self.overlay_label.setVisible(False)
            return

        max_width = self._calculate_title_max_width()
        if max_width <= 0:
            self.overlay_label.setVisible(False)
            return

        if not self.overlay_label.isVisible():
            self.overlay_label.setVisible(True)

        self.overlay_label.setMaximumWidth(max_width)
        self._apply_title_font_size()
        self.overlay_label.adjustSize()

        label_width = self.overlay_label.width()
        label_height = self.overlay_label.height()

        x = max(self.overlay_margin, (self.viewport().width() - label_width) // 2)
        y = self.viewport().height() - label_height - self.overlay_margin

        # Position relative to the widget coordinates.
        self.overlay_label.move(int(x), int(y))

    def _calculate_title_max_width(self):
        viewport_limit = max(0, self.viewport().width() - self.overlay_margin * 2)
        if viewport_limit <= 0:
            return 0

        image_rect = self._get_displayed_pixmap_rect()
        if image_rect.isNull():
            return viewport_limit

        image_width = image_rect.width()
        return max(0, min(int(image_width), viewport_limit))

    def _get_displayed_pixmap_rect(self):
        if self.pixmap_item.pixmap().isNull():
            return QRectF()

        transform = self.transform()
        return transform.mapRect(self.pixmap_item.boundingRect())

    def _apply_title_font_size(self):
        font = self.overlay_label.font()
        font.setPointSizeF(self.title_font_size)
        self.overlay_label.setFont(font)

    @staticmethod
    def _sanitize_font_size(font_size):
        try:
            size = float(font_size)
        except (TypeError, ValueError):
            return 24.0
        return max(8.0, size)
