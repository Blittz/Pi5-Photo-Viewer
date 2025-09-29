import os
import random
from datetime import datetime, time as time_cls
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from .image_viewer import ImageViewer, SUPPORTED_TRANSITIONS

SUPPORTED_IMAGE_FORMATS = ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp')

LEGACY_TRANSITION_ALIASES = {
    "slide": ["slide-horizontal", "slide-vertical"],
}


def get_all_images_from_folders(folders):
    image_paths = []
    for folder in folders:
        if not os.path.isdir(folder):
            continue
        for root, _, files in os.walk(folder):
            for file in sorted(files):
                if file.lower().endswith(SUPPORTED_IMAGE_FORMATS):
                    image_paths.append(os.path.join(root, file))
    return image_paths


class SlideshowManager(QWidget):
    def __init__(
        self,
        folders,
        shuffle=False,
        duration=5,
        motion_enabled=True,
        title_font_size=24,
        transitions=None,
        night_start=None,
        night_end=None,
    ):
        super().__init__()

        self.folders = folders
        self.shuffle = shuffle
        self.duration = duration
        self.motion_enabled = motion_enabled
        self.title_font_size = title_font_size
        self.current_index = 0
        self.current_image_path = None
        self.images = []
        self.blackout_active = False
        self.night_start = self._parse_time(night_start)
        self.night_end = self._parse_time(night_end)
        if transitions is None:
            self.transitions = list(SUPPORTED_TRANSITIONS)
        else:
            self.transitions = self._normalize_transitions(transitions)

        self.viewer = ImageViewer(
            motion_enabled=self.motion_enabled,
            title_font_size=self.title_font_size,
        )
        self.viewer.set_available_transitions(self.transitions)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.viewer)
        self.setLayout(layout)

        # Enable the slideshow window to receive keyboard focus so it can
        # react to shortcut keys such as Escape and F11.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Timer to switch images
        self.slideshow_timer = QTimer(self)
        self.slideshow_timer.timeout.connect(self.next_image)

        # Timer to refresh folder images
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_images)

        # Timer to monitor night schedule
        self.night_timer = QTimer(self)
        self.night_timer.timeout.connect(self.evaluate_night_mode)

        self.load_images()
        self.start_slideshow()

        self.slideshow_timer.start(self.duration * 1000)
        self.refresh_timer.start(60000)  # 60 seconds
        self.night_timer.start(60000)  # 60 seconds
        self.evaluate_night_mode()

    def load_images(self):
        self.images = get_all_images_from_folders(self.folders)
        if self.shuffle:
            random.shuffle(self.images)

    def refresh_images(self):
        new_images = get_all_images_from_folders(self.folders)

        if self.shuffle:
            random.shuffle(new_images)

        # Attempt to maintain current image
        if self.current_image_path in new_images:
            self.current_index = new_images.index(self.current_image_path)
        else:
            self.current_index = 0
            self.current_image_path = None

        self.images = new_images

    def start_slideshow(self):
        if not self.images:
            return
        self.show_image(self.current_index)

    def show_image(self, index):
        if not self.images or self.blackout_active:
            return
        previous_path = self.current_image_path
        self.current_index = index % len(self.images)
        self.current_image_path = self.images[self.current_index]
        transition = None
        if previous_path and self.transitions:
            transition = random.choice(self.transitions)
        self.viewer.set_image(
            self.current_image_path,
            duration=self.duration,
            transition=transition,
        )

    def next_image(self):
        if not self.images or self.blackout_active:
            return
        self.current_index = (self.current_index + 1) % len(self.images)
        self.show_image(self.current_index)

    def pause(self):
        self.slideshow_timer.stop()

    def resume(self):
        self.slideshow_timer.start(self.duration * 1000)

    def set_duration(self, seconds):
        self.duration = seconds
        self.slideshow_timer.start(self.duration * 1000)

    def toggle_shuffle(self, enabled):
        self.shuffle = enabled
        self.load_images()
        self.current_index = 0
        self.start_slideshow()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
            return
        if event.key() == Qt.Key.Key_F11:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        # Stop timers when the slideshow window closes to ensure there are no
        # lingering updates running in the background.
        self.slideshow_timer.stop()
        self.refresh_timer.stop()
        self.night_timer.stop()
        super().closeEvent(event)

    def evaluate_night_mode(self):
        if self.night_start is None or self.night_end is None:
            if self.blackout_active:
                self._exit_blackout_state()
            return

        now = datetime.now().time()
        if self._is_within_blackout(now):
            self._enter_blackout_state()
        else:
            self._exit_blackout_state()

    def _enter_blackout_state(self):
        if self.blackout_active:
            return
        self.blackout_active = True
        self.slideshow_timer.stop()
        self.viewer.show_black_screen()

    def _exit_blackout_state(self):
        if not self.blackout_active:
            return
        self.blackout_active = False
        if self.images:
            self.show_image(self.current_index)
        self.slideshow_timer.start(self.duration * 1000)

    @staticmethod
    def _normalize_transitions(transitions):
        if not transitions:
            return []

        if isinstance(transitions, str):
            transitions = [transitions]

        supported_set = set(SUPPORTED_TRANSITIONS)
        normalized = []
        for transition in transitions:
            if not isinstance(transition, str):
                continue
            transition = transition.strip().lower()
            if transition in supported_set:
                if transition not in normalized:
                    normalized.append(transition)
            elif transition in LEGACY_TRANSITION_ALIASES:
                for alias in LEGACY_TRANSITION_ALIASES[transition]:
                    if alias in supported_set and alias not in normalized:
                        normalized.append(alias)
        return normalized

    @staticmethod
    def _parse_time(value):
        if isinstance(value, time_cls):
            return value
        if isinstance(value, str):
            try:
                hour, minute = value.split(":", 1)
                return time_cls(int(hour), int(minute))
            except (ValueError, TypeError):
                return None
        return None

    def _is_within_blackout(self, current_time):
        start = self.night_start
        end = self.night_end

        if start is None or end is None:
            return False

        if start == end:
            return False

        if start < end:
            return start <= current_time < end
        return current_time >= start or current_time < end
