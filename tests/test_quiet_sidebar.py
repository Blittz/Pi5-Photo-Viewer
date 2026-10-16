"""Layout, icon, image orientation, and stationary-sidebar regressions."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from datetime import datetime
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageOps
from PyQt6.QtCore import Qt, QRect, QPoint
from PyQt6.QtGui import QColor, QFontMetrics, QPixmap
from PyQt6.QtWidgets import QApplication
from slideshow.image_viewer import ImageViewer, SUPPORTED_TRANSITIONS
from slideshow.quiet_sidebar import weather_symbol, LineIcon
from utils.solar import solar_times, MEDFORD_TIMEZONE

APP=QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


def populate(view, condition='Light Rain', temperature='72°F', missing=False):
    summary={} if missing else {'humidity':25,'wind_speed':3.44,'wind_direction':290,
                               **solar_times(datetime.now(MEDFORD_TIMEZONE).date())}
    view.set_weather_overlay({'text':f'Medford Airport\n{temperature}\n{condition}\nFeels like 70°F\n\nsolar\nSTALE — Observed Oct 15 07:50 PM PDT · Fetched Oct 15 08:03 PM PDT · Update failed; retry in 10 min',
                              'summary':summary,'icon':None})


class QuietSidebarTests(unittest.TestCase):
    def viewer(self,width=1920,height=1080,font=29):
        view=ImageViewer(motion_enabled=True,weather_font_size=font)
        view.resize(width,height); view.show(); APP.processEvents()
        self.addCleanup(view.close)
        return view

    def test_reserved_photo_area_and_stationary_transitions(self):
        view=self.viewer(); populate(view)
        self.assertEqual(view.sidebar.width(),round(view.width()*.36))
        self.assertLessEqual(view.viewport().geometry().right(),view.sidebar.geometry().left())
        photo=QPixmap(1200,900); photo.fill(QColor('navy'))
        view._apply_pixmap_immediately(photo); view.motion_timer.stop(); view.motion_anim.stop()
        self.assertAlmostEqual(view.base_transform.m11(),view.base_transform.m22())
        APP.processEvents(); baseline=view.sidebar.grab().toImage()
        for transition in SUPPORTED_TRANSITIONS:
            view.incoming_pixmap=photo; view._start_transition(transition); view.transition_anim.stop()
            view._apply_transition_progress(.5)
            self.assertEqual(view.sidebar.grab().toImage(),baseline,transition)
            view._finish_transition(); view.motion_timer.stop(); view.motion_anim.stop()
        view.apply_motion_progress(.8)
        self.assertEqual(view.sidebar.grab().toImage(),baseline)
        self.assertEqual(view.metadata_label.parent(),view.viewport())

    def test_responsive_rows_long_conditions_missing_values_and_large_temperatures(self):
        long='Light Freezing Rain and Snow with Patchy Fog and Gusty Winds'
        for width,height,font in [(1920,1080,29),(1920,1080,48),(1280,720,29),(800,480,48)]:
            with self.subTest(width=width,height=height,font=font):
                view=self.viewer(width,height,font); populate(view,long,'−123°F'); APP.processEvents()
                side=view.sidebar
                self.assertEqual(side.condition_label.text(),long)
                condition=side.condition_label; feels=side.feels_label
                self.assertEqual(condition.geometry().top(),feels.geometry().top())
                self.assertLess(condition.geometry().right(),feels.geometry().left())
                for label in [side.temperature_label,side.condition_label,side.feels_label,side.date_label,side.humidity_label,side.wind_label,side.status_label,*side.solar_labels]:
                    rect=QRect(0,0,label.width(),10000)
                    flags=int(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignTop)
                    if label.wordWrap(): flags|=int(Qt.TextFlag.TextWordWrap)
                    needed=QFontMetrics(label.font()).boundingRect(rect,flags,label.text())
                    self.assertLessEqual(needed.height(),label.height()+2,label.text())
                    if not label.wordWrap(): self.assertLessEqual(needed.width(),label.width()+2,label.text())
                populate(view,missing=True); APP.processEvents()
                self.assertEqual(side.humidity_label.text(),'Unavailable')
                self.assertEqual(side.wind_label.text(),'Unavailable')
                self.assertTrue(side.isVisible()); self.assertIn('STALE',side.status_label.text())

    def test_missing_feels_like_is_hidden_and_solar_is_enlarged(self):
        view=self.viewer(); populate(view); APP.processEvents()
        side=view.sidebar
        self.assertTrue(side.feels_label.isVisible())
        text=view._weather_text.split('\n'); text[3]=''
        view.set_weather_overlay({'text':'\n'.join(text),'summary':side._summary})
        APP.processEvents()
        self.assertFalse(side.feels_label.isVisible())
        self.assertEqual(side.feels_label.text(),'')
        for label in side.solar_titles: self.assertGreaterEqual(label.font().pixelSize(),36)
        for label in side.solar_labels:
            self.assertGreaterEqual(label.font().pixelSize(),54)
            self.assertRegex(label.text(),r'\d+:\d+ [AP]M')
        for icon in side.solar_icons: self.assertGreaterEqual(icon.width(),54)
        self.assertEqual(side.verticalScrollBar().maximum(),0)
        populate(view); APP.processEvents(); self.assertTrue(side.feels_label.isVisible())

    def test_larger_condition_and_detail_typography(self):
        view=self.viewer(); populate(view,'Clear'); APP.processEvents()
        side=view.sidebar
        self.assertGreaterEqual(side.condition_label.font().pixelSize(),46)
        self.assertTrue(side.condition_label.wordWrap())
        for _,title,value in side.detail_rows:
            self.assertGreaterEqual(title.font().pixelSize(),31)
            self.assertGreaterEqual(value.font().pixelSize(),33)
        for icon in side.detail_icons: self.assertGreaterEqual(icon.width(),36)
        for label in side.solar_labels: self.assertGreaterEqual(label.font().pixelSize(),54)
        self.assertEqual(side.verticalScrollBar().maximum(),0)

    def test_enlarged_weekdays_fit_without_changing_date_size(self):
        view=self.viewer(); populate(view,'Clear'); APP.processEvents()
        side=view.sidebar
        self.assertEqual(side.day_label.font().pixelSize(),round(75*side.scale))
        self.assertEqual(side.date_label.font().pixelSize(),round(23*side.scale))
        for weekday in ('Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'):
            side.day_label.setText(weekday); APP.processEvents()
            self.assertLessEqual(QFontMetrics(side.day_label.font()).horizontalAdvance(weekday),side.day_label.width())
            self.assertLess(side.clock_label.mapTo(side.content,QPoint(0,side.clock_label.height())).y(),side.day_label.y())
            self.assertLess(side.day_label.geometry().bottom(),side.date_label.geometry().top())
        self.assertEqual(side.verticalScrollBar().maximum(),0)

    def test_local_icons_cover_conditions_and_day_night(self):
        cases={'Clear':'clear','Partly Cloudy':'partly','Overcast':'cloud','Light Rain':'rain',
               'Snow':'snow','Thunderstorm':'storm','Freezing Rain':'ice','Fog':'fog',
               'Windy':'wind','Tornado':'tornado','Unknown':'unknown'}
        for text,expected in cases.items():
            self.assertEqual(weather_symbol(text)[0],expected)
            icon=LineIcon(expected,accent=False); icon.setFixedSize(120,120)
            icon.set_symbol(expected,False); day=icon.grab().toImage()
            icon.set_symbol(expected,True); night=icon.grab().toImage()
            self.assertNotEqual(day,night,text)
        self.assertEqual(weather_symbol('', 'https://api.weather.gov/icons/land/night/rain,20'),('rain',True))
        self.assertEqual(weather_symbol('', 'https://api.weather.gov/icons/land/day/skc'),('clear',False))

    def test_weather_toggle_and_night_schedule_controls(self):
        from slideshow.slideshow_manager import SlideshowManager
        from PyQt6.QtTest import QTest
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'photo.png'; photo=QPixmap(80,50); photo.fill(QColor('navy')); photo.save(str(path))
            manager=SlideshowManager([folder],image_paths=[str(path)],motion_enabled=False)
            self.addCleanup(manager.close); manager.resize(1920,1080); manager.show(); APP.processEvents()
            view=manager.viewer
            self.assertFalse(view.weather_container.isVisible())
            populate(view); APP.processEvents(); self.assertTrue(view.weather_container.isVisible())
            view.set_weather_overlay(None)
            self.assertFalse(view.weather_container.isVisible()); self.assertFalse(view.sidebar.source_label.isVisible())
            self.assertTrue(view.clock_label.isVisible())
            manager._enter_blackout_state()
            self.assertTrue(manager.blackout_active); self.assertFalse(manager.slideshow_timer.isActive())
            self.assertTrue(view._current_pixmap.isNull())
            manager._exit_blackout_state()
            self.assertFalse(manager.blackout_active); self.assertTrue(manager.slideshow_timer.isActive())
            self.assertFalse(view._current_pixmap.isNull())
            QTest.keyClick(manager,Qt.Key.Key_F11); APP.processEvents(); self.assertTrue(manager.isFullScreen())
            QTest.keyClick(manager,Qt.Key.Key_F11); APP.processEvents(); self.assertFalse(manager.isFullScreen())

    def test_exif_orientation_remains_non_destructive(self):
        view=self.viewer(); view.motion_enabled=False; view.set_available_transitions([])
        with tempfile.TemporaryDirectory() as folder:
            for orientation in range(1,9):
                p=Path(folder)/f'{orientation}.jpg'; im=Image.new('RGB',(80,50),'blue'); im.paste('red',(0,0,30,20))
                exif=Image.Exif(); exif[274]=orientation; im.save(p,exif=exif); original=p.read_bytes()
                view.set_image(str(p))
                with Image.open(p) as source: expected=ImageOps.exif_transpose(source).convert('RGB')
                actual=view._current_pixmap.toImage()
                self.assertEqual((actual.width(),actual.height()),expected.size)
                for x,y in [(10,10),(actual.width()-10,actual.height()-10)]:
                    self.assertLessEqual(max(abs(a-b) for a,b in zip(actual.pixelColor(x,y).getRgb()[:3],expected.getpixel((x,y)))),3)
                self.assertEqual(p.read_bytes(),original)

if __name__=='__main__': unittest.main()
