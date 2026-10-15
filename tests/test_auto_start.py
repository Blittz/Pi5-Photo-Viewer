"""Run with QT_QPA_PLATFORM=offscreen /usr/bin/python3 -B -m unittest discover -s tests."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt, QTime
from PyQt6.QtGui import QImage
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QPushButton, QWidget

from ui import main_window


APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class FakeSlideshow(QWidget):
    def __init__(self, folders, **kwargs):
        super().__init__()
        self.folders = folders
        self.options = kwargs


class AutoStartTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.photos = self.root / "photos"
        self.photos.mkdir()
        image = QImage(10, 10, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.red)
        image.save(str(self.photos / "photo.png"))
        self.settings = {
            "folders": [str(self.photos)], "shuffle": False, "motion": False,
            "duration": 9, "transitions": ["crossfade"],
            "overlay_folder_font_size": 30, "overlay_date_font_size": 22,
            "overlay_weather_font_size": 16, "weather_enabled": False,
            "night_mode_enabled": False,
        }
        self.settings_path = self.root / "settings.json"
        self.settings_path.write_text(json.dumps(self.settings))
        self.path_patch = patch.object(main_window, "SETTINGS_PATH", str(self.settings_path))
        self.path_patch.start()
        self.manager_patch = patch.object(main_window, "SlideshowManager", FakeSlideshow)
        self.manager_patch.start()
        self.windows = []

    def tearDown(self):
        for window in self.windows:
            if hasattr(window, "slideshow"):
                window.slideshow.close()
            window.close()
        APP.processEvents()
        self.manager_patch.stop()
        self.path_patch.stop()
        self.temp.cleanup()

    def open_window(self):
        window = main_window.MainWindow()
        self.windows.append(window)
        window.show()
        APP.processEvents()
        return window

    def expire(self, window):
        with patch.object(window, "auto_start_clock") as clock:
            clock.elapsed.return_value = 30000
            window.update_auto_start()

    def test_real_thirty_second_countdown_uses_saved_settings(self):
        original = self.settings_path.read_bytes()
        window = self.open_window()
        self.assertIn("30 seconds", window.auto_start_label.text())
        QTest.qWait(1100)
        self.assertIn("29 seconds", window.auto_start_label.text())
        self.assertFalse(hasattr(window, "slideshow"))
        QTest.qWait(29150)
        self.assertTrue(hasattr(window, "slideshow"))
        self.assertFalse(window.auto_start_timer.isActive())
        self.assertEqual(window.slideshow.options["duration"], 9)
        self.assertFalse(window.slideshow.options["shuffle"])
        self.assertFalse(window.slideshow.options["motion_enabled"])
        self.assertEqual(window.slideshow.options["transitions"], ["crossfade"])
        self.assertEqual(window.slideshow.options["folder_font_size"], 30)
        self.assertEqual(self.settings_path.read_bytes(), original)

    def test_cancel_button_leaves_settings_open(self):
        window = self.open_window()
        QTest.mouseClick(window.cancel_auto_start_button, Qt.MouseButton.LeftButton)
        self.expire(window)
        self.assertFalse(window.auto_start_timer.isActive())
        self.assertFalse(hasattr(window, "slideshow"))
        self.assertTrue(window.isVisible())
        self.assertIn("cancelled", window.auto_start_label.text())

    def test_start_button_starts_immediately_and_only_once(self):
        window = self.open_window()
        button = next(b for b in window.findChildren(QPushButton)
                      if b.text() == "Start Slideshow")
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        slideshow = window.slideshow
        self.expire(window)
        self.assertIs(window.slideshow, slideshow)
        self.assertFalse(window.auto_start_timer.isActive())

    def test_settings_changes_cancel_countdown(self):
        changes = [
            lambda w: w.shuffle_checkbox.toggle(),
            lambda w: w.motion_checkbox.toggle(),
            lambda w: w.duration_slider.setValue(12),
            lambda w: w.transition_checkboxes["crossfade"].toggle(),
            lambda w: w.night_start_edit.setTime(QTime(20, 15)),
            lambda w: w.weather_enable_checkbox.toggle(),
        ]
        for change in changes:
            with self.subTest(change=change):
                window = self.open_window()
                change(window)
                self.assertFalse(window.auto_start_timer.isActive())

    def test_editing_text_and_selecting_folder_cancel(self):
        window = self.open_window()
        window.weather_enable_checkbox.setChecked(True)
        # A fresh window with enabled weather fields exercises actual key input.
        self.settings["weather_enabled"] = True
        self.settings_path.write_text(json.dumps(self.settings))
        window = self.open_window()
        QTest.keyClicks(window.weather_location_input, "London")
        self.assertFalse(window.auto_start_timer.isActive())
        window = self.open_window()
        QTest.mouseClick(window.folder_list.viewport(), Qt.MouseButton.LeftButton)
        self.assertFalse(window.auto_start_timer.isActive())

    def test_folder_dialog_interaction_cancels_before_dialog(self):
        window = self.open_window()
        button = next(b for b in window.findChildren(QPushButton)
                      if b.text() == "Add Folder")
        with patch.object(main_window.QFileDialog, "getExistingDirectory", return_value="") as dialog:
            dialog.side_effect = lambda *args: self.assertFalse(window.auto_start_timer.isActive()) or ""
            QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        self.assertFalse(window.auto_start_timer.isActive())

    def test_return_to_settings_does_not_restart_countdown(self):
        window = self.open_window()
        self.expire(window)
        window.slideshow.close()
        window.hide()
        window.show()
        self.assertFalse(window.auto_start_timer.isActive())

    def test_missing_empty_and_corrupt_photo_locations(self):
        for kind in ("missing", "empty", "corrupt", "none"):
            with self.subTest(kind=kind):
                folder = self.root / kind
                if kind in ("empty", "corrupt"):
                    folder.mkdir()
                if kind == "corrupt":
                    (folder / "broken.jpg").write_text("not a photo")
                window = self.open_window()
                window.folders = [] if kind == "none" else [str(folder)]
                self.expire(window)
                self.assertFalse(hasattr(window, "slideshow"))
                self.assertFalse(window.auto_start_timer.isActive())
                self.assertTrue(window.isVisible())
                self.assertIn({"missing": "unavailable", "empty": "No usable photos",
                               "corrupt": "No usable photos", "none": "No photo folders"}[kind],
                              window.auto_start_label.text())

    def test_corrupt_images_are_excluded_from_startup(self):
        self.manager_patch.stop()
        (self.photos / "broken.png").write_text("not a photo")
        window = self.open_window()
        self.expire(window)
        window.slideshow.next_image()
        self.assertEqual(window.slideshow.images, [str(self.photos / "photo.png")])

    def test_real_slideshow_displays_valid_image_and_returns_to_settings(self):
        self.manager_patch.stop()
        window = self.open_window()
        self.expire(window)
        APP.processEvents()
        self.assertEqual(window.slideshow.current_image_path, str(self.photos / "photo.png"))
        self.assertFalse(window.slideshow.viewer._current_pixmap.isNull())
        QTest.keyClick(window.slideshow, Qt.Key.Key_Escape)
        self.assertFalse(window.slideshow.isVisible())
        self.assertTrue(window.isVisible())
        self.assertFalse(window.auto_start_timer.isActive())

    def test_real_slideshow_skips_file_corrupted_after_start(self):
        self.manager_patch.stop()
        window = self.open_window()
        self.expire(window)
        broken = self.photos / "broken.png"
        broken.write_text("not a photo")
        window.slideshow.images = [str(broken), str(self.photos / "photo.png")]
        window.slideshow.show_image(0)
        self.assertEqual(window.slideshow.images, [str(self.photos / "photo.png")])
        self.assertEqual(window.slideshow.current_image_path, str(self.photos / "photo.png"))

    def test_folder_disappearing_during_countdown_blocks_start(self):
        window = self.open_window()
        (self.photos / "photo.png").unlink()
        self.photos.rmdir()
        self.expire(window)
        self.assertFalse(hasattr(window, "slideshow"))
        self.assertIn("unavailable", window.auto_start_label.text())


if __name__ == "__main__":
    unittest.main()
