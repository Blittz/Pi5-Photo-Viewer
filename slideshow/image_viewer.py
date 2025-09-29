# File: slideshow/image_viewer.py
import math
import random
import os

from PyQt6.QtCore import Qt, QTimer, QRectF, QVariantAnimation, QEasingCurve, QPointF
from PyQt6.QtGui import QPixmap, QTransform, QPainter
from PyQt6.QtWidgets import (
    QGraphicsView,
    QGraphicsScene,
    QGraphicsPixmapItem,
    QSizePolicy,
    QLabel,
)

SUPPORTED_TRANSITIONS = [
    "crossfade",
    "slide-horizontal",
    "slide-vertical",
    "zoom",
    "carousel",
    "mosaic",
    "pixelate",
]

SUPPORTED_TRANSITIONS_SET = set(SUPPORTED_TRANSITIONS)


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
        self.pixmap_item.setZValue(0)
        self.scene.addItem(self.pixmap_item)

        self.next_pixmap_item = QGraphicsPixmapItem()
        self.next_pixmap_item.setVisible(False)
        self.next_pixmap_item.setOpacity(0.0)
        self.next_pixmap_item.setZValue(1)
        self.scene.addItem(self.next_pixmap_item)

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
        self.transition_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.transition_anim.valueChanged.connect(self._apply_transition_progress)
        self.transition_anim.finished.connect(self._finish_transition)

        self.motion_duration = 5000  # default duration (ms), can be overridden per image
        self._current_pixmap = QPixmap()
        self.base_transform = QTransform()
        self.start_scale = 1.0
        self.end_scale = 1.0
        self.total_dx = 0.0
        self.total_dy = 0.0
        self.motion_prepared = False

        # Track the currently running transition, if any.
        self.transition_active = False
        self.transition_type = None
        self.transition_data = {}
        self.transition_tiles = []
        self.incoming_pixmap = QPixmap()
        self.available_transitions = list(SUPPORTED_TRANSITIONS)

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

        self.overlay_label.setText("")

    def show_black_screen(self):
        self.motion_timer.stop()
        self.motion_anim.stop()
        self.transition_anim.stop()
        self._reset_transition_items()

        self._current_pixmap = QPixmap()
        empty_pixmap = QPixmap()
        self.pixmap_item.setPixmap(empty_pixmap)
        self.next_pixmap_item.setPixmap(empty_pixmap)
        self.overlay_label.setVisible(False)

        self.scene.setSceneRect(QRectF(self.viewport().rect()))
        self.viewport().update()

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

        if duration is not None:
            self.motion_duration = max(0, int(duration * 1000))

        folder_name = os.path.basename(os.path.dirname(image_path))
        file_name = os.path.basename(image_path)
        overlay_text = f"{folder_name}\n{file_name}" if folder_name else file_name
        self.overlay_label.setText(overlay_text)
        self.overlay_label.setVisible(True)
        self.overlay_label.raise_()

        requested_transition = None
        if isinstance(transition, str):
            trimmed = transition.strip().lower()
            if trimmed in SUPPORTED_TRANSITIONS_SET:
                requested_transition = trimmed

        if self.pixmap_item.pixmap().isNull() or self._current_pixmap.isNull():
            self._apply_pixmap_immediately(pixmap)
            return

        if self.transition_active:
            self._reset_transition_items()
            self._apply_pixmap_immediately(pixmap)
            return

        if requested_transition is None:
            if not self.available_transitions:
                self._apply_pixmap_immediately(pixmap)
                return
            requested_transition = self._choose_transition()

        self.incoming_pixmap = pixmap
        self._start_transition(requested_transition)

    def set_available_transitions(self, transitions):
        if transitions is None:
            self.available_transitions = list(SUPPORTED_TRANSITIONS)
            return

        if isinstance(transitions, str):
            transitions = [transitions]

        filtered = []
        for transition in transitions:
            if not isinstance(transition, str):
                continue
            trimmed = transition.strip().lower()
            if trimmed in SUPPORTED_TRANSITIONS_SET and trimmed not in filtered:
                filtered.append(trimmed)
        self.available_transitions = filtered

    def _apply_pixmap_immediately(self, pixmap):
        self._reset_transition_items()

        self._current_pixmap = pixmap
        self.pixmap_item.setPixmap(pixmap)

        self.scene.setSceneRect(QRectF(pixmap.rect()))
        self.resetTransform()
        self._fit_pixmap()
        self._update_overlay_position()

        if self.motion_enabled:
            self._prepare_motion_parameters()
            if self.motion_duration > 0:
                self.motion_timer.start(50)
        else:
            self.motion_prepared = False

    def _start_transition(self, transition_type):
        self.transition_active = True
        if transition_type not in SUPPORTED_TRANSITIONS_SET:
            transition_type = self._choose_transition()
        self.transition_type = transition_type
        self.transition_data = {}

        old_pixmap = self.pixmap_item.pixmap()
        new_pixmap = self.incoming_pixmap
        self.scene.setSceneRect(self._combined_scene_rect(old_pixmap, new_pixmap))

        self.pixmap_item.setPos(0, 0)
        self.pixmap_item.setScale(1.0)
        self.pixmap_item.setRotation(0.0)
        self.pixmap_item.setOpacity(1.0)
        self.pixmap_item.setTransformOriginPoint(self.pixmap_item.boundingRect().center())

        self.next_pixmap_item.setPixmap(new_pixmap)
        self.next_pixmap_item.setVisible(True)
        self.next_pixmap_item.setOpacity(1.0)
        self.next_pixmap_item.setPos(0, 0)
        self.next_pixmap_item.setScale(1.0)
        self.next_pixmap_item.setRotation(0.0)
        self.next_pixmap_item.setTransformOriginPoint(self.next_pixmap_item.boundingRect().center())

        if self.transition_type == "crossfade":
            self.pixmap_item.setOpacity(1.0)
            self.next_pixmap_item.setOpacity(0.0)
            self.transition_anim.setDuration(700)
        elif self.transition_type == "slide-horizontal":
            direction = random.choice([-1, 1])
            distance = max(old_pixmap.width(), new_pixmap.width())
            self.next_pixmap_item.setPos(direction * distance, 0)
            self.transition_data = {"direction": direction, "distance": distance}
            self.transition_anim.setDuration(650)
        elif self.transition_type == "slide-vertical":
            direction = random.choice([-1, 1])
            distance = max(old_pixmap.height(), new_pixmap.height())
            self.next_pixmap_item.setPos(0, direction * distance)
            self.transition_data = {"direction": direction, "distance": distance}
            self.transition_anim.setDuration(650)
        elif self.transition_type == "zoom":
            zoom_in = random.choice([True, False])
            start_scale = 0.7 if zoom_in else 1.2
            self.next_pixmap_item.setScale(start_scale)
            self.next_pixmap_item.setOpacity(0.0)
            self.transition_data = {"start_scale": start_scale, "end_scale": 1.0}
            self.transition_anim.setDuration(750)
        elif self.transition_type == "carousel":
            width = max(old_pixmap.width(), new_pixmap.width())
            self.pixmap_item.setTransformOriginPoint(self.pixmap_item.boundingRect().center())
            self.next_pixmap_item.setTransformOriginPoint(self.next_pixmap_item.boundingRect().center())
            self.next_pixmap_item.setScale(0.8)
            self.next_pixmap_item.setOpacity(0.2)
            self.next_pixmap_item.setPos(width * 0.55, 0)
            self.transition_data = {"width": width}
            self.transition_anim.setDuration(800)
        elif self.transition_type == "mosaic":
            self._create_mosaic_tiles(old_pixmap)
            self.pixmap_item.setOpacity(0.0)
            self.next_pixmap_item.setOpacity(0.0)
            self.next_pixmap_item.setZValue(-1)
            self.transition_anim.setDuration(900)
        elif self.transition_type == "pixelate":
            self.next_pixmap_item.setOpacity(1.0)
            self.transition_anim.setDuration(650)
        else:
            self.transition_type = "crossfade"
            self.pixmap_item.setOpacity(1.0)
            self.next_pixmap_item.setOpacity(0.0)
            self.transition_anim.setDuration(700)

        self.transition_anim.setStartValue(0.0)
        self.transition_anim.setEndValue(1.0)
        self._apply_transition_progress(0.0)
        self.transition_anim.start()

    def _choose_transition(self):
        if not self.available_transitions:
            return "crossfade"
        return random.choice(self.available_transitions)

    def _combined_scene_rect(self, old_pixmap, new_pixmap):
        widths = [pix.width() for pix in (old_pixmap, new_pixmap) if not pix.isNull()]
        heights = [pix.height() for pix in (old_pixmap, new_pixmap) if not pix.isNull()]
        if not widths or not heights:
            return QRectF(new_pixmap.rect())
        width = max(widths)
        height = max(heights)
        return QRectF(0, 0, width, height)

    def _apply_transition_progress(self, progress):
        if not self.transition_active:
            return

        progress = max(0.0, min(1.0, float(progress)))

        if self.transition_type == "crossfade":
            self.next_pixmap_item.setOpacity(progress)
            self.pixmap_item.setOpacity(1.0 - progress)
        elif self.transition_type == "slide-horizontal":
            direction = self.transition_data.get("direction", 1)
            distance = self.transition_data.get("distance", 0)
            self.next_pixmap_item.setPos(direction * (1.0 - progress) * distance, 0)
            self.pixmap_item.setPos(-direction * progress * distance, 0)
        elif self.transition_type == "slide-vertical":
            direction = self.transition_data.get("direction", 1)
            distance = self.transition_data.get("distance", 0)
            self.next_pixmap_item.setPos(0, direction * (1.0 - progress) * distance)
            self.pixmap_item.setPos(0, -direction * progress * distance)
        elif self.transition_type == "zoom":
            start_scale = self.transition_data.get("start_scale", 0.7)
            end_scale = self.transition_data.get("end_scale", 1.0)
            current_scale = start_scale + (end_scale - start_scale) * progress
            self.next_pixmap_item.setScale(current_scale)
            self.next_pixmap_item.setOpacity(progress)
            self.pixmap_item.setOpacity(1.0 - progress)
        elif self.transition_type == "carousel":
            width = self.transition_data.get("width", 0)
            self.pixmap_item.setPos(-width * 0.35 * progress, 0)
            self.pixmap_item.setOpacity(1.0 - 0.7 * progress)
            self.pixmap_item.setScale(1.0 - 0.2 * progress)
            self.pixmap_item.setRotation(-18 * progress)

            self.next_pixmap_item.setPos(width * 0.55 * (1.0 - progress) - width * 0.1, 0)
            self.next_pixmap_item.setOpacity(0.2 + 0.8 * progress)
            self.next_pixmap_item.setScale(0.8 + 0.2 * progress)
            self.next_pixmap_item.setRotation(12 * (1.0 - progress))
        elif self.transition_type == "mosaic":
            for tile, origin, offset in self.transition_tiles:
                current_x = origin.x() + offset.x() * progress
                current_y = origin.y() + offset.y() * progress
                tile.setPos(current_x, current_y)
                tile.setOpacity(1.0 - progress)
            self.next_pixmap_item.setOpacity(progress)
        elif self.transition_type == "pixelate":
            self.pixmap_item.setOpacity(1.0 - progress)
            self.next_pixmap_item.setOpacity(1.0)
            self._update_pixelated_pixmap(progress)

        self._update_overlay_position()

    def _finish_transition(self):
        if not self.transition_active:
            return

        self.transition_anim.stop()

        if self.transition_type == "pixelate" and not self.incoming_pixmap.isNull():
            self.next_pixmap_item.setPixmap(self.incoming_pixmap)

        self._cleanup_transition_tiles()

        self.pixmap_item.setOpacity(1.0)
        self.pixmap_item.setPos(0, 0)
        self.pixmap_item.setScale(1.0)
        self.pixmap_item.setRotation(0.0)
        self.pixmap_item.setTransformOriginPoint(QPointF(0, 0))

        self.next_pixmap_item.setVisible(False)
        self.next_pixmap_item.setOpacity(1.0)
        self.next_pixmap_item.setPos(0, 0)
        self.next_pixmap_item.setScale(1.0)
        self.next_pixmap_item.setRotation(0.0)
        self.next_pixmap_item.setZValue(1)

        if not self.incoming_pixmap.isNull():
            self._current_pixmap = self.incoming_pixmap
            self.pixmap_item.setPixmap(self.incoming_pixmap)
            self.scene.setSceneRect(QRectF(self.incoming_pixmap.rect()))
            self.resetTransform()
            self._fit_pixmap()
            self._update_overlay_position()

            if self.motion_enabled:
                self._prepare_motion_parameters()
                if self.motion_duration > 0:
                    self.motion_timer.start(50)
            else:
                self.motion_prepared = False

        self.transition_active = False
        self.transition_type = None
        self.transition_data = {}
        self.incoming_pixmap = QPixmap()

    def _reset_transition_items(self):
        self.transition_anim.stop()
        self._cleanup_transition_tiles()

        self.pixmap_item.setOpacity(1.0)
        self.pixmap_item.setPos(0, 0)
        self.pixmap_item.setScale(1.0)
        self.pixmap_item.setRotation(0.0)
        self.pixmap_item.setTransformOriginPoint(QPointF(0, 0))

        self.next_pixmap_item.setVisible(False)
        self.next_pixmap_item.setOpacity(1.0)
        self.next_pixmap_item.setPos(0, 0)
        self.next_pixmap_item.setScale(1.0)
        self.next_pixmap_item.setRotation(0.0)
        self.next_pixmap_item.setTransformOriginPoint(QPointF(0, 0))
        self.next_pixmap_item.setZValue(1)

        self.transition_active = False
        self.transition_type = None
        self.transition_data = {}
        self.incoming_pixmap = QPixmap()

    def _cleanup_transition_tiles(self):
        for tile, _, _ in self.transition_tiles:
            self.scene.removeItem(tile)
        self.transition_tiles = []

    def _create_mosaic_tiles(self, old_pixmap):
        self._cleanup_transition_tiles()
        if old_pixmap.isNull():
            return

        cols = 6
        rows = 5
        width = old_pixmap.width()
        height = old_pixmap.height()

        for col in range(cols):
            for row in range(rows):
                x = int(col * width / cols)
                y = int(row * height / rows)
                next_x = int((col + 1) * width / cols)
                next_y = int((row + 1) * height / rows)
                tile_width = max(1, next_x - x)
                tile_height = max(1, next_y - y)

                tile_pixmap = old_pixmap.copy(x, y, tile_width, tile_height)
                tile_item = QGraphicsPixmapItem(tile_pixmap)
                tile_item.setPos(x, y)
                tile_item.setZValue(5)
                self.scene.addItem(tile_item)

                angle = random.uniform(0, 2 * math.pi)
                distance = random.uniform(width * 0.2, width * 0.6)
                dx = math.cos(angle) * distance
                dy = math.sin(angle) * distance
                origin = QPointF(x, y)
                offset = QPointF(dx, dy)
                self.transition_tiles.append((tile_item, origin, offset))

    def _update_pixelated_pixmap(self, progress):
        if self.incoming_pixmap.isNull():
            return

        progress = max(0.0, min(1.0, float(progress)))
        width = max(1, self.incoming_pixmap.width())
        height = max(1, self.incoming_pixmap.height())

        min_ratio = 0.05
        ratio = min_ratio + (1.0 - min_ratio) * progress
        sample_width = max(1, int(width * ratio))
        sample_height = max(1, int(height * ratio))

        scaled_down = self.incoming_pixmap.scaled(
            sample_width,
            sample_height,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        pixelated = scaled_down.scaled(
            width,
            height,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        self.next_pixmap_item.setPixmap(pixelated)

    def start_motion(self):
        if not self.motion_enabled or not self.motion_prepared:
            return

        if self.pixmap_item.pixmap().isNull():
            return

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
