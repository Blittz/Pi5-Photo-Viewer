import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from datetime import datetime,timedelta,timezone,time
import unittest
from unittest.mock import patch
from PyQt6.QtCore import Qt,QRect,QPoint
from PyQt6.QtGui import QColor,QFontMetrics,QImage
from PyQt6.QtWidgets import QApplication,QWidget
from slideshow.health_indicator import HealthEdge
from slideshow.slideshow_manager import SlideshowManager
from utils.event_client import EventClient
from utils.scheduled_events import countdown,event_view,validate_snapshot

APP=QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


def data(now,seconds=12300):
    return validate_snapshot({'schema_version':1,'refresh_ok':True,
      'last_attempted_refresh':now.isoformat(),'last_successful_refresh':now.isoformat(),
      'servers':[{'id':'1','name':'Example server','refresh_ok':True,'last_successful_refresh':now.isoformat()}],
      'events':[{'id':'10','server_id':'1','title':'An unexpected journey across forgotten mountains with old friends and a returning visitor',
                 'start_at':(now+timedelta(seconds=seconds)).isoformat(),'end_at':None,
                 'status':'scheduled','kind':'external','channel_id':None}]})


class AlertTests(unittest.TestCase):
    def manager(self):
        with patch('utils.weather_client.WeatherClient.fetch_weather'),patch('utils.health_monitor.HealthMonitor._start_probe'),patch.object(EventClient,'refresh'):
            manager=SlideshowManager([],image_paths=[],weather_enabled=True,weather_font_size=29,
                                     night_start='21:00',night_end='05:30',night_display_brightness=40)
            manager.resize(1920,1080);manager.show();APP.processEvents()
        manager.health_monitor.timer.stop();manager.event_timer.stop();manager.event_client.timer.stop()
        manager.evaluate_night_mode(time(12))
        self.addCleanup(manager.close)
        return manager

    def test_gradient_five_percent_soft_corners_static_centre_and_dimming(self):
        window=QWidget();window.resize(1920,1080);window.show()
        edge=HealthEdge(window);edge.setGeometry(window.rect());edge.set_health((),imminent=True)
        APP.processEvents();self.assertEqual(edge.fade_width(),54)
        first=edge.grab().toImage().convertToFormat(QImage.Format.Format_ARGB32)
        self.assertGreater(first.pixelColor(960,8).alpha(),first.pixelColor(960,28).alpha())
        self.assertGreater(first.pixelColor(960,28).alpha(),first.pixelColor(960,50).alpha())
        self.assertEqual(first.pixelColor(960,55).alpha(),0)
        self.assertEqual(first.pixelColor(960,540).alpha(),0)
        self.assertLess(first.pixelColor(0,0).alpha(),first.pixelColor(960,1).alpha())
        self.assertEqual(first,edge.grab().toImage().convertToFormat(QImage.Format.Format_ARGB32))
        edge.set_health((),40,imminent=True)
        self.assertLess(edge.grab().toImage().pixelColor(960,1).blue(),first.pixelColor(960,1).blue())
        edge.set_health(('Weather stale',),40,imminent=True);self.assertEqual(edge.mode,'health')
        edge.set_health((),40,imminent=True);self.assertEqual(edge.mode,'event')
        window.resize(1280,720);edge.setGeometry(window.rect());self.assertEqual(edge.fade_width(),36)
        window.close()

    def test_caption_photo_only_priority_resize_clickthrough_and_bottom_unchanged(self):
        manager=self.manager();now=datetime.now(timezone.utc)
        manager.viewer._photo_folder_text='Example folder';manager.viewer._photo_date_text='October 16, 2026'
        manager.viewer._update_metadata_label();APP.processEvents()
        bottom=manager.viewer.metadata_label
        before=(bottom.text(),bottom.geometry(),manager.viewer.viewport().size())
        manager.event_client.snapshot=data(now);manager._refresh_event_view();APP.processEvents()
        caption=manager.viewer.event_caption
        self.assertTrue(caption.isVisible());self.assertEqual(manager.health_edge.mode,'event')
        self.assertIn('Starts in 3h',caption.countdown.text())
        self.assertTrue(caption.title.wordWrap());self.assertEqual(caption.parentWidget(),manager.viewer.viewport())
        self.assertEqual(before,(bottom.text(),bottom.geometry(),manager.viewer.viewport().size()))
        self.assertTrue(caption.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))
        center=caption.geometry().center()
        self.assertIsNone(manager.viewer.viewport().childAt(center))
        for _ in range(2):manager.health_monitor.record('bot',False,'Photo bot service stopped')
        self.assertEqual(manager.health_edge.mode,'health');self.assertTrue(caption.isVisible())
        manager.idle_cursor._hide_cursor();manager._refresh_event_view();APP.processEvents();self.assertTrue(manager.idle_cursor.hidden)
        for size in [(1280,720),(1920,1080)]:
            manager.resize(*size);APP.processEvents()
            self.assertLessEqual(caption.geometry().right(),manager.viewer.viewport().width())
            self.assertAlmostEqual(caption.geometry().center().x(),manager.viewer.viewport().rect().center().x(),delta=1)
            self.assertLess(caption.geometry().bottom(),bottom.geometry().top())
            for label in caption.labels:
                bounds=QFontMetrics(label.font()).boundingRect(QRect(0,0,label.width(),10000),int(Qt.TextFlag.TextWordWrap),label.text())
                self.assertLessEqual(bounds.height(),label.height())
        manager.evaluate_night_mode(time(22));APP.processEvents();self.assertFalse(caption.isVisible())
        self.assertEqual(caption.view,{})
        self.assertTrue(manager.night_display.event_panel.isVisible())
        manager.evaluate_night_mode(time(12));APP.processEvents();self.assertTrue(caption.isVisible())
        manager.health_monitor.record('bot',True);self.assertEqual(manager.health_edge.mode,'event')

    def test_countdown_actual_timestamp_final_minute_and_caption_clearing(self):
        now=datetime.now(timezone.utc)
        self.assertEqual(countdown(12*60),'Starts in 12m')
        self.assertEqual(countdown(3*3600+25*60),'Starts in 3h 25m')
        self.assertEqual(countdown(59),'Starts in less than a minute')
        snapshot=data(now,120)
        self.assertEqual(event_view(snapshot,now=now+timedelta(seconds=61))['countdown'],'Starts in less than a minute')
        manager=self.manager();manager.event_client.snapshot=data(now,40);manager._refresh_event_view();APP.processEvents()
        self.assertEqual(manager.viewer.event_caption.countdown.text(),'Starts in less than a minute')
        self.assertNotIn('0m',manager.night_display.event_panel.detail.text())
        for kind in ('stale','canceled','active','far','started'):
            snapshot=data(now,40)
            if kind=='stale':manager.event_client.read_failed=True
            if kind in ('canceled','active'):snapshot['events'][0]['status']=kind
            if kind=='far':snapshot=data(now,25*3600)
            if kind=='started':snapshot=data(now,-10)
            manager.event_client.snapshot=snapshot;manager._refresh_event_view();APP.processEvents()
            self.assertFalse(manager.viewer.event_caption.isVisible(),kind)
            manager.event_client.read_failed=False


if __name__=='__main__':unittest.main()
