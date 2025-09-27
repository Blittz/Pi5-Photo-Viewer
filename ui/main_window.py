from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel, QListWidget, QListWidgetItem,
    QFileDialog, QHBoxLayout, QCheckBox, QSlider
)
from PyQt6.QtCore import Qt
from slideshow.slideshow_manager import SlideshowManager
from utils.file_loader import count_images_in_folder
import os
import json

SETTINGS_PATH = "settings.json"

def load_json_settings():
    try:
        with open(SETTINGS_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_json_settings(data):
    with open(SETTINGS_PATH, "w") as f:
        json.dump(data, f, indent=4)

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pi Photo Viewer")
        self.folders = []
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Folder list
        self.folder_list = QListWidget()
        layout.addWidget(QLabel("Selected Folders:"))
        layout.addWidget(self.folder_list)

        # Folder controls
        folder_btns = QHBoxLayout()
        add_btn = QPushButton("Add Folder")
        add_btn.clicked.connect(self.select_folders)
        folder_btns.addWidget(add_btn)

        remove_btn = QPushButton("Remove Selected")
        remove_btn.clicked.connect(self.remove_selected_folder)
        folder_btns.addWidget(remove_btn)

        up_btn = QPushButton("Move Up")
        up_btn.clicked.connect(self.move_folder_up)
        folder_btns.addWidget(up_btn)

        down_btn = QPushButton("Move Down")
        down_btn.clicked.connect(self.move_folder_down)
        folder_btns.addWidget(down_btn)

        layout.addLayout(folder_btns)

        # Shuffle checkbox
        self.shuffle_checkbox = QCheckBox("Shuffle Photos")
        self.shuffle_checkbox.setChecked(True)
        layout.addWidget(self.shuffle_checkbox)

        # Motion effects checkbox
        self.motion_checkbox = QCheckBox("Enable Motion Effects")
        self.motion_checkbox.setChecked(True)
        layout.addWidget(self.motion_checkbox)

        # Duration slider
        duration_layout = QHBoxLayout()
        duration_label = QLabel("Image Duration (sec):")
        self.duration_slider = QSlider(Qt.Orientation.Horizontal)
        self.duration_slider.setRange(2, 30)
        self.duration_slider.setValue(5)
        self.duration_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.duration_slider.setTickInterval(1)
        self.duration_slider.valueChanged.connect(self.update_duration_label)

        self.duration_display = QLabel("5s")
        duration_layout.addWidget(duration_label)
        duration_layout.addWidget(self.duration_slider)
        duration_layout.addWidget(self.duration_display)

        layout.addLayout(duration_layout)

        # Folder name font size slider
        folder_title_layout = QHBoxLayout()
        folder_title_label = QLabel("Folder Name Font Size (pt):")
        self.folder_title_slider = QSlider(Qt.Orientation.Horizontal)
        self.folder_title_slider.setRange(12, 48)
        self.folder_title_slider.setValue(24)
        self.folder_title_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.folder_title_slider.setTickInterval(2)
        self.folder_title_slider.valueChanged.connect(self.update_folder_title_label)

        self.folder_title_display = QLabel()
        self.update_folder_title_label()
        folder_title_layout.addWidget(folder_title_label)
        folder_title_layout.addWidget(self.folder_title_slider)
        folder_title_layout.addWidget(self.folder_title_display)

        layout.addLayout(folder_title_layout)

        # File name font size slider
        file_title_layout = QHBoxLayout()
        file_title_label = QLabel("File Name Font Size (pt):")
        self.file_title_slider = QSlider(Qt.Orientation.Horizontal)
        self.file_title_slider.setRange(12, 48)
        self.file_title_slider.setValue(24)
        self.file_title_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.file_title_slider.setTickInterval(2)
        self.file_title_slider.valueChanged.connect(self.update_file_title_label)

        self.file_title_display = QLabel()
        self.update_file_title_label()
        file_title_layout.addWidget(file_title_label)
        file_title_layout.addWidget(self.file_title_slider)
        file_title_layout.addWidget(self.file_title_display)

        layout.addLayout(file_title_layout)

        # Start slideshow
        start_btn = QPushButton("Start Slideshow")
        start_btn.clicked.connect(self.start_slideshow)
        layout.addWidget(start_btn)

    def update_duration_label(self):
        self.duration_display.setText(f"{self.duration_slider.value()}s")

    def select_folders(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder", os.path.expanduser("~"))
        if folder:
            if folder not in self.folders:
                image_count = count_images_in_folder(folder)
                self.folders.append(folder)
                item = QListWidgetItem(f"{folder} ({image_count} photos)")
                self.folder_list.addItem(item)

    def remove_selected_folder(self):
        selected = self.folder_list.currentRow()
        if selected >= 0:
            self.folder_list.takeItem(selected)
            self.folders.pop(selected)

    def move_folder_up(self):
        index = self.folder_list.currentRow()
        if index > 0:
            self.folders[index], self.folders[index - 1] = self.folders[index - 1], self.folders[index]
            self.refresh_folder_list()
            self.folder_list.setCurrentRow(index - 1)

    def move_folder_down(self):
        index = self.folder_list.currentRow()
        if index < len(self.folders) - 1:
            self.folders[index], self.folders[index + 1] = self.folders[index + 1], self.folders[index]
            self.refresh_folder_list()
            self.folder_list.setCurrentRow(index + 1)

    def refresh_folder_list(self):
        self.folder_list.clear()
        for path in self.folders:
            image_count = count_images_in_folder(path)
            self.folder_list.addItem(f"{path} ({image_count} photos)")

    def start_slideshow(self):
        if not self.folders:
            return
        shuffle = self.shuffle_checkbox.isChecked()
        duration = self.duration_slider.value()
        motion_enabled = self.motion_checkbox.isChecked()
        folder_title_font_size = self.folder_title_slider.value()
        file_title_font_size = self.file_title_slider.value()

        self.slideshow = SlideshowManager(
            self.folders,
            shuffle=shuffle,
            duration=duration,
            motion_enabled=motion_enabled,
            folder_title_font_size=folder_title_font_size,
            file_title_font_size=file_title_font_size,
        )
        self.slideshow.showFullScreen()

    def load_settings(self):
        data = load_json_settings()

        self.folders = data.get("folders", [])
        shuffle = data.get("shuffle", True)
        motion = data.get("motion", True)
        duration = data.get("duration", 5)
        folder_title_font_size = data.get("overlay_folder_font_size")
        file_title_font_size = data.get("overlay_file_font_size")

        legacy_title_font_size = data.get("overlay_title_font_size")
        if legacy_title_font_size is not None:
            if folder_title_font_size is None:
                folder_title_font_size = legacy_title_font_size
            if file_title_font_size is None:
                file_title_font_size = legacy_title_font_size

        if folder_title_font_size is None or file_title_font_size is None:
            legacy_percentage = data.get("overlay_percentage")
            if legacy_percentage is not None:
                converted = self.convert_legacy_overlay_percentage(legacy_percentage)
                if folder_title_font_size is None:
                    folder_title_font_size = converted
                if file_title_font_size is None:
                    file_title_font_size = converted

        if folder_title_font_size is None:
            folder_title_font_size = 24
        if file_title_font_size is None:
            file_title_font_size = 24

        self.shuffle_checkbox.setChecked(shuffle)
        self.motion_checkbox.setChecked(motion)
        self.duration_slider.setValue(duration)
        self.folder_title_slider.setValue(int(round(folder_title_font_size)))
        self.file_title_slider.setValue(int(round(file_title_font_size)))
        self.update_folder_title_label()
        self.update_file_title_label()

        self.folder_list.clear()
        for folder in self.folders:
            image_count = count_images_in_folder(folder)
            item = QListWidgetItem(f"{folder} ({image_count} photos)")
            self.folder_list.addItem(item)

    def save_settings(self):
        data = {
            "folders": self.folders,
            "shuffle": self.shuffle_checkbox.isChecked(),
            "motion": self.motion_checkbox.isChecked(),
            "duration": self.duration_slider.value(),
            "overlay_folder_font_size": self.folder_title_slider.value(),
            "overlay_file_font_size": self.file_title_slider.value(),
        }
        save_json_settings(data)

    def closeEvent(self, event):
        self.save_settings()
        super().closeEvent(event)

    def update_folder_title_label(self):
        self.folder_title_display.setText(f"{self.folder_title_slider.value()} pt")

    def update_file_title_label(self):
        self.file_title_display.setText(f"{self.file_title_slider.value()} pt")

    @staticmethod
    def convert_legacy_overlay_percentage(percentage):
        try:
            value = float(percentage)
        except (TypeError, ValueError):
            return 24

        min_slider = 10.0
        max_slider = 100.0
        min_font = 12.0
        max_font = 36.0

        clamped = max(min_slider, min(value, max_slider))
        ratio = (clamped - min_slider) / (max_slider - min_slider)
        return min_font + ratio * (max_font - min_font)
