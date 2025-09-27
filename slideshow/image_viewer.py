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
    QWidget,
    QVBoxLayout,
)


class ImageViewer(QGraphicsView):
    def __init__(
        self,
        motion_enabled=True,
        folder_title_font_size=24,
        file_title_font_size=24,
    ):
        super().__init__()

        self.motion_enabled = motion_enabled
        self.folder_title_font_size = self._sanitize_font_size(folder_title_font_size)
        self.file_title_font_size = self._sanitize_font_size(file_title_font_size)
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

        self.overlay_widget = QWidget(self)
        self.overlay_widget.setVisible(False)
        self.overlay_widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.overlay_widget.setStyleSheet(
            "background-color: rgba(0, 0, 0, 180);"
            "border-radius: 12px;"
        )

        overlay_layout = QVBoxLayout(self.overlay_widget)
        overlay_layout.setContentsMargins(14, 10, 14, 12)
        overlay_layout.setSpacing(2)

        self.folder_label = QLabel()
        self.folder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.folder_label.setStyleSheet("color: white;")
        self.folder_label.setWordWrap(True)

        self.file_label = QLabel()
        self.file_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.file_label.setStyleSheet("color: white;")
        self.file_label.setWordWrap(True)

        overlay_layout.addWidget(self.folder_label)
        overlay_layout.addWidget(self.file_label)

        self.overlay_margin = 20

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._current_pixmap.isNull():
            self._fit_pixmap()
        self._update_overlay_position()

    def set_image(self, image_path, duration=None):
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            self.overlay_widget.setVisible(False)
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

        has_folder = bool(folder_name)
        has_file = bool(file_name)

        self.folder_label.setVisible(has_folder)
        self.folder_label.setText(folder_name if has_folder else "")

        self.file_label.setVisible(has_file)
        self.file_label.setText(file_name if has_file else "")

        should_show_overlay = has_folder or has_file
        self.overlay_widget.setVisible(should_show_overlay)

        if should_show_overlay:
            self.overlay_widget.raise_()
            self._apply_title_font_sizes()
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

    def set_folder_title_font_size(self, font_size):
        sanitized = self._sanitize_font_size(font_size)
        if math.isclose(self.folder_title_font_size, sanitized):
            return
        self.folder_title_font_size = sanitized
        self._update_overlay_position()

    def set_file_title_font_size(self, font_size):
        sanitized = self._sanitize_font_size(font_size)
        if math.isclose(self.file_title_font_size, sanitized):
            return
        self.file_title_font_size = sanitized
        self._update_overlay_position()

    def _update_overlay_position(self):
        if not self.overlay_widget.isVisible():
            return

        max_width = self._calculate_title_max_width()
        if max_width <= 0:
            self.overlay_widget.setVisible(False)
            return

        self._apply_title_font_sizes()
        self.overlay_widget.setMaximumWidth(max_width)
        self.overlay_widget.adjustSize()

        widget_width = self.overlay_widget.width()
        widget_height = self.overlay_widget.height()

        x = max(self.overlay_margin, (self.viewport().width() - widget_width) // 2)
        y = self.viewport().height() - widget_height - self.overlay_margin

        # Position relative to the widget coordinates.
        self.overlay_widget.move(int(x), int(y))

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

    def _apply_title_font_sizes(self):
        if self.folder_label.isVisible():
            folder_font = self.folder_label.font()
            folder_font.setPointSizeF(self.folder_title_font_size)
            self.folder_label.setFont(folder_font)

        if self.file_label.isVisible():
            file_font = self.file_label.font()
            file_font.setPointSizeF(self.file_title_font_size)
            self.file_label.setFont(file_font)

    @staticmethod
    def _sanitize_font_size(font_size):
        try:
            size = float(font_size)
        except (TypeError, ValueError):
            return 24.0
        return max(8.0, size)
