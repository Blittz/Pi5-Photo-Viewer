# File: slideshow/image_viewer.py
import math
import random
import os
import html
from datetime import datetime, date
from dataclasses import asdict, is_dataclass
from pathlib import Path

from PyQt6.QtCore import (
    Qt,
    QTimer,
    QRectF,
    QVariantAnimation,
    QEasingCurve,
    QPointF,
    QUrl,
)
from PyQt6.QtGui import (
    QPixmap,
    QTransform,
    QPainter,
    QFont,
    QFontMetrics,
    QFontDatabase,
)
from PyQt6.QtWidgets import (
    QGraphicsView,
    QGraphicsScene,
    QGraphicsPixmapItem,
    QSizePolicy,
    QLabel,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
)
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from PIL import Image, ExifTags

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

EXIF_DATE_TAG_NAMES = ("DateTimeOriginal", "DateTimeDigitized", "DateTime")
EXIF_TAG_NAME_TO_ID = {name: tag for tag, name in ExifTags.TAGS.items()}


class ImageViewer(QGraphicsView):
    _emoji_font_family = None
    _WEATHER_EMOJI_SEQUENCES = (
        "🌬️",
        "🌬",
        "🌅",
        "🌇",
        "💧",
        "☀️",
        "☀",
        "☁️",
        "☁",
        "❄️",
        "❄",
        "⛈️",
        "⛈",
        "🌧️",
        "🌧",
        "🌨️",
        "🌨",
    )

    def __init__(
        self,
        motion_enabled=True,
        folder_font_size=24,
        date_font_size=20,
        weather_font_size=18,
    ):
        super().__init__()

        self.motion_enabled = motion_enabled
        self.folder_font_size = self._sanitize_font_size(folder_font_size)
        self.date_font_size = self._sanitize_font_size(date_font_size)
        self.weather_font_size = self._sanitize_font_size(weather_font_size)
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

        self.metadata_label = QLabel(self)
        self.metadata_label.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom
        )
        self.metadata_label.setStyleSheet(
            "color: white; background-color: rgba(0, 0, 0, 180);"
            "padding: 6px 14px; border-radius: 12px;"
        )
        self.metadata_label.setWordWrap(False)
        self.metadata_label.setVisible(False)
        self.metadata_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.metadata_label.setTextFormat(Qt.TextFormat.RichText)
        self.metadata_horizontal_padding = 28  # matches padding: 6px 14px

        self.weather_container = QWidget(self)
        self.weather_container.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )
        self.weather_container.setVisible(False)

        self.weather_layout = QVBoxLayout(self.weather_container)
        self.weather_layout.setContentsMargins(12, 10, 12, 10)
        self.weather_layout.setSpacing(6)

        self.weather_header_layout = QHBoxLayout()
        self.weather_header_layout.setContentsMargins(0, 0, 0, 0)
        self.weather_header_layout.setSpacing(10)
        self.weather_layout.addLayout(self.weather_header_layout)

        self.weather_location_label = QLabel(self.weather_container)
        self.weather_location_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        self.weather_location_label.setWordWrap(True)
        self.weather_location_label.setVisible(False)
        self.weather_location_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )
        self.weather_header_layout.addWidget(self.weather_location_label)

        self.weather_icon_label = QLabel(self.weather_container)
        self.weather_icon_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
        )
        self.weather_icon_label.setVisible(False)
        self.weather_icon_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )
        self.weather_header_layout.addWidget(self.weather_icon_label)

        self.weather_condition_label = QLabel(self.weather_container)
        self.weather_condition_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        self.weather_condition_label.setWordWrap(True)
        self.weather_condition_label.setVisible(False)
        self.weather_condition_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )
        self.weather_header_layout.addWidget(self.weather_condition_label)
        self.weather_header_layout.addStretch(1)

        self.weather_text_label = QLabel(self.weather_container)
        self.weather_text_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        self.weather_text_label.setWordWrap(True)
        self.weather_text_label.setTextFormat(Qt.TextFormat.RichText)
        self.weather_text_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )
        self.weather_layout.addWidget(self.weather_text_label)

        self._apply_weather_stylesheet()

        self.overlay_margin = 20

        self._photo_folder_text = ""
        self._photo_date_text = ""
        self._weather_text = ""
        self._weather_icon_key = None
        self._weather_icon_pixmap = QPixmap()
        self._weather_icon_size = 0
        self._icon_cache = {}
        self._pending_icon_reply = None

        self._update_weather_icon_size()
        self._pending_icon_key = None
        self._network_manager = QNetworkAccessManager(self)

    def show_black_screen(self):
        self.motion_timer.stop()
        self.motion_anim.stop()
        self.transition_anim.stop()
        self._reset_transition_items()

        self._current_pixmap = QPixmap()
        empty_pixmap = QPixmap()
        self.pixmap_item.setPixmap(empty_pixmap)
        self.next_pixmap_item.setPixmap(empty_pixmap)
        self._photo_folder_text = ""
        self._photo_date_text = ""
        self._weather_text = ""
        self._weather_icon_key = None
        self._cancel_pending_icon_request()
        self._clear_weather_icon()
        self._update_metadata_label()
        self._update_weather_display()

        self.scene.setSceneRect(QRectF(self.viewport().rect()))
        self.viewport().update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._current_pixmap.isNull():
            self._fit_pixmap()
        self._update_metadata_label()
        self._update_overlay_positions()

    def set_image(self, image_path, duration=None, transition=None):
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            self._photo_folder_text = ""
            self._photo_date_text = ""
            self._update_metadata_label()
            return

        self.motion_timer.stop()
        self.motion_anim.stop()
        self.transition_anim.stop()

        if duration is not None:
            self.motion_duration = max(0, int(duration * 1000))

        self._set_photo_metadata(image_path)
        self._update_metadata_label()
        self._update_overlay_positions()

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
        self._update_overlay_positions()

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

        self._update_overlay_positions()

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
            self._update_overlay_positions()

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
        self._update_overlay_positions()

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

    def set_metadata_font_sizes(self, folder_font_size, date_font_size):
        sanitized_folder = self._sanitize_font_size(folder_font_size)
        sanitized_date = self._sanitize_font_size(date_font_size)
        if (
            math.isclose(self.folder_font_size, sanitized_folder)
            and math.isclose(self.date_font_size, sanitized_date)
        ):
            return
        self.folder_font_size = sanitized_folder
        self.date_font_size = sanitized_date
        self._update_metadata_label()
        self._update_overlay_positions()

    def set_weather_font_size(self, font_size):
        sanitized = self._sanitize_font_size(font_size)
        if math.isclose(self.weather_font_size, sanitized):
            return
        self.weather_font_size = sanitized
        self._update_weather_icon_size()
        self._apply_weather_stylesheet()
        self._update_weather_display()
        self._update_overlay_positions()

    def _calculate_weather_icon_size(self):
        point_size = max(1.0, float(self.weather_font_size))
        try:
            dpi_x = float(self.logicalDpiX())
            dpi_y = float(self.logicalDpiY())
            dpi = max(dpi_x, dpi_y)
        except Exception:
            dpi = 96.0
        if dpi <= 0:
            dpi = 96.0
        pixels_per_point = dpi / 72.0
        return max(8.0, point_size * 2.0 * pixels_per_point)

    def _update_weather_icon_size(self):
        calculated_size = self._calculate_weather_icon_size()
        if math.isclose(self._weather_icon_size, calculated_size):
            return
        self._weather_icon_size = calculated_size

        if self._weather_icon_key:
            cached = self._icon_cache.get(self._weather_icon_key)
            if isinstance(cached, QPixmap) and not cached.isNull():
                self._apply_weather_icon(cached)
                return

        if not self._weather_icon_pixmap.isNull():
            self._apply_weather_icon(self._weather_icon_pixmap)
        else:
            target = int(self._weather_icon_size)
            self.weather_icon_label.setFixedSize(target, target)

    def _update_overlay_positions(self):
        self._update_weather_position()
        self._update_metadata_position()

    def _calculate_metadata_max_width(self):
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

    def _update_metadata_label(self):
        folder_text = self._photo_folder_text.strip()
        date_text = self._photo_date_text.strip()

        max_width = self._calculate_metadata_max_width()
        available_width = None
        if max_width > 0:
            available_width = max(0, max_width - self.metadata_horizontal_padding)

        segments = []
        if folder_text:
            display_folder = self._elide_metadata_text(
                folder_text, self.folder_font_size, available_width
            )
            segments.append(
                "<div style=\"font-size:{:.1f}pt; font-weight:600;\">{}</div>".format(
                    self.folder_font_size,
                    html.escape(display_folder),
                )
            )
        if date_text:
            display_date = self._elide_metadata_text(
                date_text, self.date_font_size, available_width
            )
            segments.append(
                "<div style=\"font-size:{:.1f}pt;\">{}</div>".format(
                    self.date_font_size,
                    html.escape(display_date),
                )
            )

        if segments:
            combined = "".join(segments)
            self.metadata_label.setText(
                f"<div style='text-align:center; white-space:nowrap;'>{combined}</div>"
            )
            self.metadata_label.setVisible(True)
            self.metadata_label.raise_()
        else:
            self.metadata_label.setText("")
            self.metadata_label.setVisible(False)

    def _update_metadata_position(self):
        if not self.metadata_label.isVisible():
            return

        max_width = self._calculate_metadata_max_width()
        if max_width <= 0:
            self.metadata_label.setVisible(False)
            return

        self.metadata_label.setMaximumWidth(max_width)
        self.metadata_label.adjustSize()

        label_width = self.metadata_label.width()
        label_height = self.metadata_label.height()

        x = (self.viewport().width() - label_width) / 2
        min_x = self.overlay_margin
        max_x = self.viewport().width() - label_width - self.overlay_margin
        if max_x < min_x:
            x = min_x
        else:
            x = max(min_x, min(x, max_x))
        y = self.viewport().height() - label_height - self.overlay_margin
        self.metadata_label.move(int(x), int(y))

    def _set_photo_metadata(self, image_path):
        folder_name = os.path.basename(os.path.dirname(image_path))
        photo_date = self._extract_photo_date(image_path)
        if not photo_date:
            try:
                timestamp = os.path.getmtime(image_path)
            except (OSError, ValueError):
                timestamp = None
            if timestamp is not None:
                fallback_dt = datetime.fromtimestamp(timestamp)
                photo_date = self._format_display_date(fallback_dt)
        self._photo_folder_text = folder_name or ""
        self._photo_date_text = photo_date or ""

    def _extract_photo_date(self, image_path):
        try:
            with Image.open(image_path) as img:
                if hasattr(img, "getexif"):
                    exif_data = img.getexif()
                else:
                    exif_data = img._getexif()
        except Exception:
            return ""

        if not exif_data:
            return ""

        for tag_name in EXIF_DATE_TAG_NAMES:
            tag_id = EXIF_TAG_NAME_TO_ID.get(tag_name)
            if tag_id is None:
                continue
            value = exif_data.get(tag_id)
            formatted = self._format_exif_datetime(value)
            if formatted:
                return formatted
        return ""

    @staticmethod
    def _format_exif_datetime(value):
        if value is None:
            return ""

        if isinstance(value, datetime):
            return ImageViewer._format_display_date(value)

        if isinstance(value, date):
            return ImageViewer._format_display_date(
                datetime(value.year, value.month, value.day)
            )

        if isinstance(value, bytes):
            try:
                value = value.decode("utf-8", errors="ignore")
            except Exception:
                try:
                    value = value.decode(errors="ignore")
                except Exception:
                    return ""

        text = str(value).strip()
        if not text:
            return ""

        replacements = {"/": "-", "T": " ", "\u0000": ""}
        for src, dst in replacements.items():
            text = text.replace(src, dst)

        datetime_formats = [
            "%Y:%m:%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y:%m:%d %H:%M",
            "%Y-%m-%d %H:%M",
            "%Y:%m:%d",
            "%Y-%m-%d",
        ]

        for fmt in datetime_formats:
            try:
                parsed = datetime.strptime(text, fmt)
                return ImageViewer._format_display_date(parsed)
            except ValueError:
                continue

        return text

    @staticmethod
    def _format_display_date(value):
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, date):
            dt = datetime(value.year, value.month, value.day)
        else:
            return ""

        month = dt.strftime("%B")
        return f"{month} {dt.day}, {dt.year}"

    def _elide_metadata_text(self, text, point_size, max_width):
        if not text:
            return ""
        if not max_width or max_width <= 0:
            return text

        font = QFont(self.metadata_label.font())
        font.setPointSizeF(point_size)
        metrics = QFontMetrics(font)
        return metrics.elidedText(text, Qt.TextElideMode.ElideMiddle, int(max_width))

    def set_weather_overlay(self, weather):
        text, icon_hint = self._normalize_weather_overlay(weather)
        icon_key, icon_url = self._resolve_icon_sources(icon_hint)

        text_changed = text != self._weather_text
        icon_changed = icon_key != self._weather_icon_key

        self._weather_text = text

        if icon_changed:
            self._set_weather_icon(icon_key, icon_url)
        elif text_changed:
            self._update_weather_display()

    def _update_weather_display(self):
        display_text = (self._weather_text or "").strip()
        lines = [line.strip() for line in display_text.splitlines() if line.strip()]
        has_icon = not self._weather_icon_pixmap.isNull()
        if has_icon:
            self.weather_icon_label.setPixmap(self._weather_icon_pixmap)
        self.weather_icon_label.setVisible(has_icon)

        location_text = ""
        condition_text = ""
        body_lines = []

        if lines:
            candidate_header = lines[0]
            header_location = ""
            header_condition = ""

            for separator in (" – ", " - ", " — "):
                if separator in candidate_header:
                    left, right = candidate_header.split(separator, 1)
                    header_location = left.strip()
                    header_condition = right.strip()
                    break

            if not header_location and not header_condition:
                if has_icon or len(lines) > 1:
                    header_location = candidate_header.strip()
                else:
                    body_lines = lines

            if header_location or header_condition:
                location_text = header_location
                condition_text = header_condition
                if not body_lines:
                    body_lines = lines[1:]
        if not body_lines and not location_text and not condition_text:
            body_lines = lines

        if location_text and (condition_text or has_icon):
            location_display = f"{location_text} -"
        else:
            location_display = location_text

        body_text = "\n".join(body_lines)
        body_html = self._render_weather_body_html(body_text)

        self.weather_location_label.setText(location_display)
        self.weather_location_label.setVisible(bool(location_display))

        self.weather_condition_label.setText(condition_text)
        self.weather_condition_label.setVisible(bool(condition_text))

        if body_html:
            self.weather_text_label.setText(body_html)
        else:
            self.weather_text_label.clear()
        self.weather_text_label.setVisible(bool(body_text))

        should_show = (
            self.weather_location_label.isVisible()
            or self.weather_condition_label.isVisible()
            or self.weather_text_label.isVisible()
            or has_icon
        )
        self.weather_container.setVisible(should_show)
        if should_show:
            self.weather_container.raise_()

        self._update_overlay_positions()

    def _apply_weather_stylesheet(self):
        emoji_font_family = self._ensure_weather_icon_font()

        self.weather_container.setStyleSheet(
            "background-color: rgba(0, 0, 0, 180); border-radius: 12px;"
        )
        header_style = (
            "background-color: transparent; "
            f"color: white; font-size: {self.weather_font_size:.1f}pt;"
        )

        def compose_font_family_css(base_family):
            if base_family:
                return f" font-family: \"{base_family}\", sans-serif;"
            return " font-family: sans-serif;"

        location_font_css = compose_font_family_css(
            self.weather_location_label.font().family()
        )
        condition_font_css = compose_font_family_css(
            self.weather_condition_label.font().family()
        )
        text_font_css = compose_font_family_css(self.weather_text_label.font().family())

        self.weather_location_label.setStyleSheet(
            header_style + location_font_css + " font-weight: 600;"
        )
        self.weather_condition_label.setStyleSheet(header_style + condition_font_css)
        self.weather_text_label.setStyleSheet(
            "background-color: transparent; "
            f"color: white; font-size: {self.weather_font_size:.1f}pt;"
            + text_font_css
        )
        self.weather_icon_label.setStyleSheet(
            "background: transparent; "
            f"font-family: \"{emoji_font_family}\", sans-serif;"
        )
        self.weather_icon_label.setFont(QFont(emoji_font_family))

    def _render_weather_body_html(self, body_text):
        if not body_text:
            return ""

        emoji_font_family = self._ensure_weather_icon_font()
        escaped = html.escape(body_text)
        for sequence in sorted(self._WEATHER_EMOJI_SEQUENCES, key=len, reverse=True):
            if not sequence:
                continue
            escaped_sequence = html.escape(sequence)
            if escaped_sequence not in escaped:
                continue
            replacement = (
                f"<span style=\"font-family: '{emoji_font_family}', sans-serif;\">"
                f"{escaped_sequence}</span>"
            )
            escaped = escaped.replace(escaped_sequence, replacement)
        return escaped.replace("\n", "<br/>")

    @classmethod
    def _ensure_weather_icon_font(cls):
        if cls._emoji_font_family:
            return cls._emoji_font_family

        emoji_font_paths = (
            Path("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"),
            Path("/usr/share/fonts/opentype/noto/NotoColorEmoji.ttf"),
        )

        for path in emoji_font_paths:
            if not path.exists():
                continue
            font_id = QFontDatabase.addApplicationFont(str(path))
            if font_id == -1:
                continue
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                cls._emoji_font_family = families[0]
                break

        if not cls._emoji_font_family:
            cls._emoji_font_family = "Noto Color Emoji"

        return cls._emoji_font_family

    def _update_weather_position(self):
        if not self.weather_container.isVisible():
            return

        max_width = max(0, self.viewport().width() - self.overlay_margin * 2)
        if max_width <= 0:
            self.weather_container.setVisible(False)
            return

        margins = self.weather_layout.contentsMargins()
        content_width = max_width - margins.left() - margins.right()
        if content_width < 0:
            content_width = 0

        for label in (
            self.weather_location_label,
            self.weather_condition_label,
            self.weather_text_label,
        ):
            if label.isVisible():
                label.setMaximumWidth(content_width or max_width)
            else:
                label.setMaximumWidth(0)

        self.weather_container.setMaximumWidth(max_width)
        self.weather_container.adjustSize()

        x = self.overlay_margin
        y = self.overlay_margin
        self.weather_container.move(int(x), int(y))

    def _normalize_weather_overlay(self, weather):
        if weather is None:
            return "", None
        if isinstance(weather, str):
            return weather.strip(), None
        if is_dataclass(weather):
            weather = asdict(weather)

        if isinstance(weather, dict):
            icon_hint = None
            if "text" in weather:
                text_value = str(weather.get("text") or "").strip()
                icon_hint = (
                    weather.get("icon")
                    or weather.get("icon_code")
                    or weather.get("icon_url")
                )
            else:
                text_value = ImageViewer._normalize_weather_text(weather)
                icon_hint = weather.get("icon")

            if isinstance(icon_hint, dict):
                icon_hint = icon_hint.get("url") or icon_hint.get("code")

            if not text_value:
                text_value = ImageViewer._normalize_weather_text(weather)

            icon_hint = str(icon_hint).strip() if isinstance(icon_hint, str) else None
            if icon_hint == "":
                icon_hint = None

            return text_value, icon_hint

        return str(weather).strip(), None

    @staticmethod
    def _normalize_weather_text(weather):
        if weather is None:
            return ""
        if isinstance(weather, str):
            return weather.strip()
        if is_dataclass(weather):
            weather = asdict(weather)
        if isinstance(weather, dict):
            condition = weather.get("condition")
            temperature = weather.get("temperature")
            extra = weather.get("extra")
            parts = []
            if temperature is not None:
                parts.append(str(temperature))
            if condition:
                parts.append(str(condition))
            if extra:
                parts.append(str(extra))
            return " – ".join(part for part in parts if part).strip()
        return str(weather).strip()

    def _resolve_icon_sources(self, icon_hint):
        if not icon_hint:
            return None, None

        hint = icon_hint.strip()
        if not hint:
            return None, None

        if hint.startswith("http://") or hint.startswith("https://"):
            return hint, hint

        return hint, f"https://openweathermap.org/img/wn/{hint}@2x.png"

    def _set_weather_icon(self, icon_key, icon_url):
        self._cancel_pending_icon_request()

        if not icon_key or not icon_url:
            self._weather_icon_key = None
            self._clear_weather_icon()
            self._update_weather_display()
            return

        self._weather_icon_key = icon_key

        cached = self._icon_cache.get(icon_key)
        if isinstance(cached, QPixmap) and not cached.isNull():
            self._apply_weather_icon(cached)
            self._update_weather_display()
            return

        url = QUrl(icon_url)
        if not url.isValid():
            self._weather_icon_key = None
            self._clear_weather_icon()
            self._update_weather_display()
            return

        request = QNetworkRequest(url)
        self._pending_icon_reply = self._network_manager.get(request)
        self._pending_icon_key = icon_key
        self._pending_icon_reply.finished.connect(self._on_icon_download_finished)  # type: ignore[arg-type]
        self._update_weather_display()

    def _apply_weather_icon(self, pixmap):
        if pixmap.isNull():
            self._clear_weather_icon()
            return

        target_size = int(self._weather_icon_size)
        scaled = pixmap.scaled(
            target_size,
            target_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._weather_icon_pixmap = scaled
        self.weather_icon_label.setPixmap(scaled)
        self.weather_icon_label.setFixedSize(target_size, target_size)
        self.weather_icon_label.setVisible(True)

    def _clear_weather_icon(self):
        self._weather_icon_pixmap = QPixmap()
        self.weather_icon_label.clear()
        self.weather_icon_label.setVisible(False)

    def _cancel_pending_icon_request(self):
        if self._pending_icon_reply is None:
            return
        try:
            self._pending_icon_reply.finished.disconnect(self._on_icon_download_finished)  # type: ignore[arg-type]
        except TypeError:
            pass
        self._pending_icon_reply.abort()
        self._pending_icon_reply.deleteLater()
        self._pending_icon_reply = None
        self._pending_icon_key = None

    def _on_icon_download_finished(self):
        reply = self.sender()
        if not isinstance(reply, QNetworkReply):
            return

        if reply is not self._pending_icon_reply:
            reply.deleteLater()
            return

        icon_key = self._pending_icon_key
        self._pending_icon_reply = None
        self._pending_icon_key = None

        if reply.error() != QNetworkReply.NetworkError.NoError:
            reply.deleteLater()
            if icon_key == self._weather_icon_key:
                self._weather_icon_key = None
                self._clear_weather_icon()
                self._update_weather_display()
            return

        data = bytes(reply.readAll())
        reply.deleteLater()

        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            if icon_key == self._weather_icon_key:
                self._weather_icon_key = None
                self._clear_weather_icon()
                self._update_weather_display()
            return

        self._icon_cache[icon_key] = pixmap

        if icon_key == self._weather_icon_key:
            self._apply_weather_icon(pixmap)
            self._update_weather_display()

    @staticmethod
    def _sanitize_font_size(font_size):
        try:
            size = float(font_size)
        except (TypeError, ValueError):
            return 24.0
        return max(8.0, size)
