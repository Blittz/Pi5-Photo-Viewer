from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel, QListWidget, QListWidgetItem,
    QFileDialog, QHBoxLayout, QCheckBox, QSlider, QGridLayout, QLineEdit
)
from PyQt6.QtCore import Qt
from slideshow.slideshow_manager import SlideshowManager
from utils.file_loader import count_images_in_folder
import os
import json

SETTINGS_PATH = "settings.json"

TRANSITION_OPTIONS = [
    ("Crossfade", "crossfade"),
    ("Slide (Horizontal)", "slide-horizontal"),
    ("Slide (Vertical)", "slide-vertical"),
    ("Zoom", "zoom"),
    ("Carousel", "carousel"),
    ("Mosaic", "mosaic"),
    ("Pixelate", "pixelate"),
]

LEGACY_TRANSITION_ALIASES = {
    "slide": ["slide-horizontal", "slide-vertical"],
}

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

        # Weather settings
        self.weather_enable_checkbox = QCheckBox("Enable Weather Overlay")
        layout.addWidget(self.weather_enable_checkbox)

        weather_layout = QGridLayout()

        weather_layout.addWidget(QLabel("API Key:"), 0, 0)
        self.weather_api_key_input = QLineEdit()
        self.weather_api_key_input.setPlaceholderText("OpenWeather API key")
        weather_layout.addWidget(self.weather_api_key_input, 0, 1)

        weather_layout.addWidget(QLabel("Location:"), 1, 0)
        self.weather_location_input = QLineEdit()
        self.weather_location_input.setPlaceholderText("City name or latitude,longitude")
        weather_layout.addWidget(self.weather_location_input, 1, 1)

        weather_layout.addWidget(QLabel("Units:"), 2, 0)
        self.weather_units_input = QLineEdit()
        self.weather_units_input.setPlaceholderText("metric / imperial / standard")
        weather_layout.addWidget(self.weather_units_input, 2, 1)

        weather_layout.setColumnStretch(1, 1)
        layout.addLayout(weather_layout)

        self.weather_enable_checkbox.toggled.connect(self.update_weather_fields_enabled)
        self.update_weather_fields_enabled()

        # Transition selection
        layout.addWidget(QLabel("Enabled Transitions:"))
        transitions_layout = QGridLayout()
        self.transition_checkboxes = {}
        for index, (label_text, key) in enumerate(TRANSITION_OPTIONS):
            checkbox = QCheckBox(label_text)
            checkbox.setChecked(True)
            self.transition_checkboxes[key] = checkbox
            row = index // 3
            column = index % 3
            transitions_layout.addWidget(checkbox, row, column)
        layout.addLayout(transitions_layout)

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

        # Title font size slider
        title_layout = QHBoxLayout()
        title_label = QLabel("Title Font Size (pt):")
        self.title_slider = QSlider(Qt.Orientation.Horizontal)
        self.title_slider.setRange(12, 48)
        self.title_slider.setValue(24)
        self.title_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.title_slider.setTickInterval(2)
        self.title_slider.valueChanged.connect(self.update_title_label)

        self.title_display = QLabel()
        self.update_title_label()
        title_layout.addWidget(title_label)
        title_layout.addWidget(self.title_slider)
        title_layout.addWidget(self.title_display)

        layout.addLayout(title_layout)

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
        title_font_size = self.title_slider.value()
        selected_transitions = [
            key for key, checkbox in self.transition_checkboxes.items() if checkbox.isChecked()
        ]

        self.slideshow = SlideshowManager(
            self.folders,
            shuffle=shuffle,
            duration=duration,
            motion_enabled=motion_enabled,
            title_font_size=title_font_size,
            transitions=selected_transitions,
        )
        self.slideshow.showFullScreen()

    def load_settings(self):
        data = load_json_settings()

        self.folders = data.get("folders", [])
        shuffle = data.get("shuffle", True)
        motion = data.get("motion", True)
        duration = data.get("duration", 5)
        title_font_size = data.get("overlay_title_font_size")
        saved_transitions = self.normalize_transition_keys(data.get("transitions"))
        if title_font_size is None:
            legacy_percentage = data.get("overlay_percentage")
            if legacy_percentage is not None:
                title_font_size = self.convert_legacy_overlay_percentage(legacy_percentage)
            else:
                title_font_size = 24

        if not saved_transitions:
            saved_transitions = [key for _, key in TRANSITION_OPTIONS]

        self.shuffle_checkbox.setChecked(shuffle)
        self.motion_checkbox.setChecked(motion)
        self.duration_slider.setValue(duration)
        self.title_slider.setValue(int(round(title_font_size)))
        self.update_title_label()

        weather_enabled = data.get("weather_enabled", False)

        weather_api_key = data.get("weather_api_key")
        if weather_api_key is None:
            weather_api_key = ""
        else:
            weather_api_key = str(weather_api_key)

        weather_location = data.get("weather_location")
        if weather_location is None:
            weather_location = ""
        else:
            weather_location = str(weather_location)

        weather_units = data.get("weather_units")
        if not weather_units:
            weather_units = "metric"
        else:
            weather_units = str(weather_units)

        self.weather_enable_checkbox.setChecked(weather_enabled)
        self.weather_api_key_input.setText(weather_api_key)
        self.weather_location_input.setText(weather_location)
        self.weather_units_input.setText(weather_units)
        self.update_weather_fields_enabled()

        for key, checkbox in self.transition_checkboxes.items():
            checkbox.setChecked(key in saved_transitions)

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
            "overlay_title_font_size": self.title_slider.value(),
            "transitions": self.normalize_transition_keys([
                key for key, checkbox in self.transition_checkboxes.items() if checkbox.isChecked()
            ]),
            "weather_enabled": self.weather_enable_checkbox.isChecked(),
            "weather_api_key": self.weather_api_key_input.text().strip(),
            "weather_location": self.weather_location_input.text().strip(),
            "weather_units": self.weather_units_input.text().strip() or "metric",
        }
        save_json_settings(data)

    def closeEvent(self, event):
        self.save_settings()
        super().closeEvent(event)

    def update_title_label(self):
        self.title_display.setText(f"{self.title_slider.value()} pt")

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

    @staticmethod
    def normalize_transition_keys(keys):
        if not keys:
            return []

        if isinstance(keys, str):
            keys = [keys]

        valid_keys = {key for _, key in TRANSITION_OPTIONS}
        normalized = []
        for key in keys:
            if not isinstance(key, str):
                continue
            key = key.strip().lower()
            if key in valid_keys:
                if key not in normalized:
                    normalized.append(key)
            elif key in LEGACY_TRANSITION_ALIASES:
                for alias in LEGACY_TRANSITION_ALIASES[key]:
                    if alias not in normalized:
                        normalized.append(alias)
        return normalized

    def update_weather_fields_enabled(self):
        enabled = self.weather_enable_checkbox.isChecked()
        for widget in (
            self.weather_api_key_input,
            self.weather_location_input,
            self.weather_units_input,
        ):
            widget.setEnabled(enabled)
