"""Night palette, persisted intensity, scheduled transitions, and live data."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from datetime import datetime, date, time, timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PyQt6.QtCore import Qt, QRect, QPoint
from PyQt6.QtGui import QImage, QFontMetrics, QColor
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest
from slideshow.night_display import NightDisplay, night_brightness, DEFAULT_NIGHT_BRIGHTNESS
from slideshow.slideshow_manager import SlideshowManager
from utils.solar import MEDFORD_TIMEZONE, solar_times
from ui import main_window

APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class NightDisplayTests(unittest.TestCase):
    def manager(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / 'photo.png'
        image = QImage(80, 50, QImage.Format.Format_RGB32); image.fill(Qt.GlobalColor.blue); image.save(str(path))
        with patch('utils.weather_client.WeatherClient.fetch_weather'):
            manager = SlideshowManager([tmp.name], image_paths=[str(path)], weather_enabled=True,
                                       night_start='21:00', night_end='05:30', motion_enabled=False,
                                       weather_font_size=29)
        manager.resize(1920,1080); manager.show(); APP.processEvents()
        self.addCleanup(manager.close)
        return manager

    def payload(self):
        return {'city':'Medford Airport', 'condition':'Clear', 'temperature':66,
                'humidity':30, 'wind_speed':6, 'wind_direction':270,
                'feels_like':None, 'observed_at':datetime.now(MEDFORD_TIMEZONE).isoformat()}

    def test_schedule_boundaries_pause_resume_and_day_preservation(self):
        manager=self.manager(); manager._on_weather_success(self.payload())
        for clock, expected in [(time(20,59),False),(time(21),True),(time(23,59),True),
                                (time(0),True),(time(5,29),True),(time(5,30),False)]:
            manager.evaluate_night_mode(clock); APP.processEvents()
            self.assertEqual(manager.blackout_active,expected)
            self.assertEqual(manager.display_stack.currentWidget(),manager.night_display if expected else manager.viewer)
            self.assertEqual(manager.slideshow_timer.isActive(),not expected)
            if expected:
                self.assertFalse(manager.viewer.isVisible())
                self.assertFalse(manager.viewer.metadata_label.isVisible())
                self.assertFalse(manager.viewer.motion_anim.state().value)
                manager.resume(); manager.set_duration(12)
                self.assertFalse(manager.slideshow_timer.isActive())
            else:
                self.assertFalse(manager.viewer._current_pixmap.isNull())
                self.assertEqual(manager.viewer.sidebar.width(),round(1920*.36))
        manager.night_start=time(10);manager.night_end=time(12)
        manager.evaluate_night_mode(time(10));self.assertTrue(manager.blackout_active)
        manager.evaluate_night_mode(time(12));self.assertFalse(manager.blackout_active)
        manager.night_start=manager.night_end=time(10)
        manager.evaluate_night_mode(time(10));self.assertFalse(manager.blackout_active)

    def test_updates_stale_status_clock_and_idle_cursor_during_night(self):
        manager=self.manager();manager.evaluate_night_mode(time(22));manager._on_weather_success(self.payload())
        night=manager.night_display
        self.assertTrue(night.clock_timer.isActive());self.assertTrue(manager.weather_status_timer.isActive())
        self.assertTrue(manager.weather_timer.isActive());self.assertFalse(manager.slideshow_timer.isActive())
        self.assertEqual(night.temperature_label.text(),'66°F');self.assertFalse(night.feels_label.isVisible())
        changed=self.payload();changed.update(temperature=60,feels_like=58,condition='Light Rain')
        manager._on_weather_success(changed)
        self.assertEqual(night.temperature_label.text(),'60°F');self.assertTrue(night.feels_label.isVisible())
        manager._on_weather_error('NWS request failed')
        self.assertIn('STALE',night.status_label.text());self.assertIn('Update failed',night.status_label.text())
        self.assertEqual(night.temperature_label.text(),'60°F');self.assertEqual(manager.weather_timer.interval(),600000)
        self.assertTrue(all(l.text()!='Unavailable' for l in night.solar_labels))
        manager.idle_cursor.timer.setInterval(25);manager.idle_cursor.show_cursor();manager.idle_cursor.timer.start()
        QTest.qWait(60);self.assertTrue(manager.idle_cursor.hidden)
        QTest.mouseMove(night.viewport(),QPoint(15,15));APP.processEvents();self.assertFalse(manager.idle_cursor.hidden)

    def test_date_rollover_updates_solar_without_network(self):
        manager=self.manager();manager.evaluate_night_mode(time(22));manager._on_weather_success(self.payload())
        tomorrow=datetime.now(MEDFORD_TIMEZONE)+timedelta(days=1)
        class Tomorrow(datetime):
            @classmethod
            def now(cls,tz=None):
                return tomorrow.astimezone(tz) if tz else tomorrow.replace(tzinfo=None)
        with patch('slideshow.slideshow_manager.datetime',Tomorrow):manager._refresh_weather_overlay()
        self.assertEqual(manager._solar_date,tomorrow.date())
        self.assertEqual(manager._solar_events,solar_times(tomorrow.date()))
        for label,key in zip(manager.night_display.solar_labels,('sunrise','sunset')):
            self.assertEqual(label.text(),datetime.fromtimestamp(solar_times(tomorrow.date())[key],MEDFORD_TIMEZONE).strftime('%I:%M %p').lstrip('0'))

    def test_dim_palette_and_missing_long_data_fit(self):
        manager=self.manager();manager.evaluate_night_mode(time(22))
        night=manager.night_display
        payload=self.payload();payload['condition']='Light Freezing Rain and Snow with Patchy Fog and Gusty Winds'
        manager._on_weather_success(payload);APP.processEvents()
        self.assertGreater(night.clock_label.font().pixelSize(),night.temperature_label.font().pixelSize())
        self.assertEqual(night.verticalScrollBar().maximum(),0)
        for label in [night.condition_label,night.status_label,night.day_label,night.date_label,night.wind_label,*night.solar_labels]:
            flags=int(Qt.TextFlag.TextWordWrap) if label.wordWrap() else 0
            bounds=QFontMetrics(label.font()).boundingRect(QRect(0,0,label.width(),10000),flags,label.text())
            self.assertLessEqual(bounds.height(),label.height()+4,label.text())
        self.assertLess(max(QColor(night.primary).getRgb()[:3]),80)
        before=night.primary;night.set_brightness(60);self.assertNotEqual(night.primary,before)
        self.assertEqual(night.brightness,60)
        self.assertEqual(night.icon.background,'#070809')
        self.assertLessEqual(max(QColor(night.primary).getRgb()[:3]),178)
        self.assertFalse(night.feels_label.isVisible())
        for value,expected in [(None,30),('invalid',30),(float('nan'),30),(True,30),(0,5),(200,100)]:
            self.assertEqual(night_brightness(value),expected)

    def test_brightness_settings_round_trip_and_default(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'settings.json'
            path.write_text('{"folders":[],"night_mode_enabled":true,"night_start":"21:00","night_end":"05:30"}')
            with patch.object(main_window,'SETTINGS_PATH',str(path)):
                window=main_window.MainWindow()
                self.assertEqual(window.night_brightness_slider.value(),DEFAULT_NIGHT_BRIGHTNESS)
                window.night_brightness_slider.setValue(45);window.save_settings()
                restored=main_window.MainWindow()
                self.assertEqual(restored.night_brightness_slider.value(),45)
                self.assertEqual(restored.night_start_edit.time().toString('HH:mm'),'21:00')
                self.assertEqual(restored.night_end_edit.time().toString('HH:mm'),'05:30')
                window.close();restored.close()

if __name__=='__main__':unittest.main()
