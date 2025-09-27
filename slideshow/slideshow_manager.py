from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QKeyEvent, QFont
from slideshow.image_viewer import ImageViewer
from utils.file_loader import load_images_from_folders
import os
import random

class SlideshowManager(QWidget):
    def __init__(self, folders, shuffle=False, duration=5, motion_enabled=True):
        super().__init__()
        self.setWindowTitle("Slideshow")
        self.setStyleSheet("background-color: black;")

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.viewer = ImageViewer()
        self.layout.addWidget(self.viewer)

        # Overlay label at bottom center
        self.overlay = QLabel(self)
        self.overlay.setStyleSheet("""
            color: white;
            background-color: rgba(0, 0, 0, 150);
            padding: 10px;
        """)
        self.overlay.setFont(QFont("Arial", 16))
        self.overlay.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        self.overlay.setFixedHeight(50)
        self.overlay.raise_()

        # Load images
        images = load_images_from_folders(folders)
        if shuffle:
            random.shuffle(images)

        self.images = images
        self.index = 0
        self.duration = duration
        self.paused = False
        self.is_fullscreen = True
        self.motion_enabled = motion_enabled

        # Timer for slideshow
        self.timer = QTimer()
        self.timer.timeout.connect(self.next_image)
        self.timer.start(self.duration * 1000)

        self.next_image()

    def next_image(self):
        if not self.images:
            return

        image_path = self.images[self.index]
        self.viewer.show_image(
            image_path,
            duration=self.duration * 1000,
            motion=self.motion_enabled
        )
        self.update_overlay(image_path)
        self.index = (self.index + 1) % len(self.images)

    def prev_image(self):
        if not self.images:
            return
        self.index = (self.index - 2) % len(self.images)
        self.next_image()

    def toggle_pause(self):
        if self.paused:
            self.timer.start(self.duration * 1000)
        else:
            self.timer.stop()
        self.paused = not self.paused
        current_image = self.images[(self.index - 1) % len(self.images)]
        self.update_overlay(current_image)

    def update_overlay(self, image_path):
        folder = os.path.basename(os.path.dirname(image_path))
        filename = os.path.basename(image_path)
        text = f"{folder} / {filename}"
        if self.paused:
            text += "   [PAUSED]"
        self.overlay.setText(text)

    def resizeEvent(self, event):
        self.overlay.resize(self.width(), 50)
        self.overlay.move(0, self.height() - self.overlay.height())

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.close()
        elif key == Qt.Key.Key_Space:
            self.toggle_pause()
        elif key == Qt.Key.Key_Right:
            self.next_image()
        elif key == Qt.Key.Key_Left:
            self.prev_image()
        elif key == Qt.Key.Key_F11:
            self.toggle_fullscreen()

    def toggle_fullscreen(self):
        if self.is_fullscreen:
            self.showNormal()
        else:
            self.showFullScreen()
        self.is_fullscreen = not self.is_fullscreen
