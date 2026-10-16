"""Read-only health probes, debouncing, full-window rendering and recovery."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone, time
from unittest.mock import patch

from PyQt6.QtCore import Qt, QProcess, QTimer, QPoint, QObject
from PyQt6.QtGui import QImage, QFontMetrics, QColor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QWidget, QPushButton
from slideshow.health_indicator import HealthEdge, warning_color
from slideshow.slideshow_manager import SlideshowManager
from utils import health_probe, health_monitor

APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class ProbeTests(unittest.TestCase):
    def test_empty_mounted_share_is_healthy_without_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            mount = Path(folder); photos = mount/'photos'; photos.mkdir()
            identity = ('test', mount.stat().st_dev)
            with patch.object(health_probe, 'mount_identity', return_value=identity):
                self.assertEqual(health_probe.check_share(mount, [photos]), (True, ''))
            self.assertEqual(list(photos.iterdir()), [])

    def test_unmounted_never_opens_underlying_directory(self):
        with patch.object(health_probe, 'mount_identity', return_value=None), patch.object(health_probe.os, 'open') as opened:
            self.assertEqual(health_probe.check_share('/example/share', [])[0], False)
            opened.assert_not_called()

    def test_unreadable_missing_symlink_and_changed_mount_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            mount = Path(folder); target = mount/'photos'; target.mkdir()
            identity = ('test', mount.stat().st_dev)
            with patch.object(health_probe, 'mount_identity', return_value=identity):
                with patch.object(health_probe.os, 'scandir', side_effect=PermissionError):
                    with self.assertRaises(PermissionError): health_probe.check_share(mount, [])
                with self.assertRaises(FileNotFoundError): health_probe.check_share(mount, [mount/'missing'])
                (mount/'link').symlink_to(target, target_is_directory=True)
                with self.assertRaises(OSError): health_probe.check_share(mount, [mount/'link'])
            with patch.object(health_probe, 'mount_identity', side_effect=[identity, ('changed', identity[1])]):
                self.assertFalse(health_probe.check_share(mount, [target])[0])

    def test_service_active_stopped_and_inaccessible(self):
        for code, output, healthy in [(0, 'active\n', True), (0, 'inactive\n', False),
                                       (0, 'failed\n', False), (1, '', False)]:
            with patch.object(health_probe.subprocess, 'run', return_value=subprocess.CompletedProcess([], code, output, '')) as run:
                self.assertEqual(health_probe.check_bot()[0], healthy)
                args, kwargs = run.call_args
                self.assertNotIn('sudo', args[0]); self.assertEqual(kwargs['timeout'], 3)

    def test_mountinfo_requires_expected_cifs_root(self):
        table='1 0 0:9 / /example/share rw - ext4 /dev/example rw\n2 0 0:10 / /example/other rw - cifs //example/share rw\n'
        with patch.object(Path, 'read_text', return_value=table):
            self.assertIsNone(health_probe.mount_identity('/example/share'))
        with patch.object(Path, 'read_text', return_value='2 0 0:10 / /example/share rw - cifs //example/share rw\n'):
            self.assertEqual(health_probe.mount_identity('/example/share'), ('2', os.makedev(0,10)))


class HealthTests(unittest.TestCase):
    def manager(self):
        with patch('utils.weather_client.WeatherClient.fetch_weather'), patch.object(health_monitor.HealthMonitor, '_start_probe'):
            manager = SlideshowManager([], image_paths=[], weather_enabled=True,
                                       weather_font_size=29, night_start='21:00', night_end='05:30',
                                       night_display_brightness=40)
            manager.resize(1920,1080); manager.show(); APP.processEvents()
        manager.health_monitor.timer.stop()
        self.addCleanup(manager.close)
        return manager

    def test_debounce_compact_order_transition_logs_and_recovery(self):
        monitor=health_monitor.HealthMonitor([], lambda age:(True,''))
        monitor.timer.stop(); self.addCleanup(monitor.stop)
        published=[]; monitor.issuesChanged.connect(published.append)
        with self.assertLogs('utils.health_monitor', level='INFO') as logs:
            monitor.record('bot', False, 'Photo bot service stopped')
            self.assertEqual(published, [])
            monitor.record('bot', True)
            monitor.record('bot', False, 'Photo bot service stopped')
            monitor.record('bot', False, 'Photo bot service stopped')
            for _ in range(5): monitor.record('bot', False, 'Photo bot service stopped')
            monitor.record('share', False, 'Photo share not mounted')
            monitor.record('share', False, 'Photo share not mounted')
            self.assertEqual(published[-1], ('Photo share not mounted','Photo bot service stopped'))
            monitor.record('bot', True);monitor.record('share', True)
        self.assertEqual(published[-1], ())
        self.assertEqual(len(logs.output), 4)

    def test_weather_existing_rules_disabled_pending_and_recovery(self):
        manager=self.manager()
        self.assertEqual(manager._health_weather_check(0),(None,''))
        self.assertEqual(manager._health_weather_check(90),(False,'Weather unavailable'))
        now=datetime.now(timezone.utc)
        for age, stale in [(0,False),(89,False),(91,True),(-6,True)]:
            payload={'observed_at':(now-timedelta(minutes=age)).isoformat()}
            manager._latest_weather_summary=payload
            self.assertEqual(manager._weather_is_stale(payload,now),stale)
            self.assertEqual(manager._health_weather_check(100)[0],not stale)
        for observed in (None,'invalid',now.replace(tzinfo=None).isoformat()):
            self.assertTrue(manager._weather_is_stale({'observed_at':observed},now))
        manager._latest_weather_summary={'observed_at':now.isoformat()}
        manager._weather_error='NWS request failed'
        self.assertFalse(manager._health_weather_check(100)[0])
        manager._weather_error=None
        self.assertTrue(manager._health_weather_check(100)[0])
        manager.weather_enabled=False;manager._weather_error='failed'
        self.assertTrue(manager._health_weather_check(100)[0])

    def test_full_window_edge_day_night_resize_and_clear(self):
        manager=self.manager();manager.evaluate_night_mode(time(12))
        manager._on_weather_success({'condition':'Clear','temperature':65,'humidity':40,'wind_speed':3,
                                     'observed_at':datetime.now(timezone.utc).isoformat()})
        issues=('Photo share not mounted','Weather stale','Photo bot service stopped')
        for key,message in zip(('share','weather','bot'),issues):
            manager.health_monitor.record(key,False,message);manager.health_monitor.record(key,False,message)
        APP.processEvents()
        edge=manager.health_edge
        self.assertEqual(edge.geometry(),manager.rect())
        self.assertTrue(edge.isVisible())
        self.assertTrue(edge.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))
        self.assertNotEqual(edge.focusPolicy(),Qt.FocusPolicy.StrongFocus)
        self.assertEqual(manager.viewer.sidebar.width(),round(1920*.36))
        self.assertTrue(manager.viewer.sidebar.health_notice.isVisible())
        manager.idle_cursor._hide_cursor()
        manager._apply_health_issues(())
        manager._apply_health_issues(issues)
        APP.processEvents()
        self.assertTrue(manager.idle_cursor.hidden)
        self.assertEqual(manager.viewer.sidebar.verticalScrollBar().maximum(),0)
        manager.evaluate_night_mode(time(22));APP.processEvents()
        self.assertEqual(edge.brightness,40)
        self.assertTrue(manager.night_display.health_notice.isVisible())
        self.assertLess(warning_color(40).red(),warning_color().red())
        for size in [(1280,720),(1920,1080)]:
            manager.resize(*size);APP.processEvents()
            self.assertEqual(edge.geometry(),manager.rect())
        for key in ('share','weather','bot'):manager.health_monitor.record(key,True)
        self.assertFalse(edge.isVisible())
        self.assertFalse(manager.night_display.health_notice.isVisible())
        self.assertFalse(manager.viewer.sidebar.health_notice.isVisible())

    def test_first_weather_response_settles_without_healthy_scrollbar(self):
        manager=self.manager();manager.evaluate_night_mode(time(12))
        QTest.qWait(50)
        manager._on_weather_success({'condition':'Clear','temperature':None,'humidity':None,
                                     'wind_speed':0,'wind_direction':0,
                                     'observed_at':datetime.now(timezone.utc).isoformat()})
        QTest.qWait(50)
        self.assertEqual(manager.viewer.sidebar.verticalScrollBar().maximum(),0)
        self.assertFalse(manager.health_edge.isVisible())

    def test_edge_pixels_fade_centre_unchanged_and_clicks_pass_through(self):
        window=QWidget();window.resize(320,200);window.setStyleSheet('background:#242628')
        button=QPushButton('control',window);button.setGeometry(70,60,100,40)
        clicked=[];button.clicked.connect(lambda:clicked.append(True))
        window.show();edge=HealthEdge(window);edge.setGeometry(window.rect())
        edge.set_health(('Weather stale',));APP.processEvents()
        self.assertIs(window.childAt(100,80),button)
        QTest.mouseClick(window.childAt(100,80),Qt.MouseButton.LeftButton)
        self.assertEqual(clicked,[True])
        image=window.grab().toImage()
        self.assertGreater(image.pixelColor(1,100).red(),image.pixelColor(8,100).red())
        self.assertEqual(image.pixelColor(30,150),QColor('#242628'))
        window.close()

    def test_closing_parent_cancels_and_reaps_probe_jobs(self):
        class SlowProcess(QProcess):
            def start(self, program, arguments):
                super().start('/usr/bin/python3',['-c','import time; time.sleep(5)'])
        with patch.object(health_monitor,'QProcess',SlowProcess):
            parent=QObject()
            monitor=health_monitor.HealthMonitor([],lambda age:(True,''),parent)
            monitor.timer.stop();monitor.check()
            jobs=list(monitor._processes.values())
            parent.deleteLater()
            QTest.qWait(150)
            for job in jobs:
                self.assertNotIn(job,health_monitor._ACTIVE_PROBES)

    def test_probes_timeout_off_ui_and_do_not_overlap(self):
        class SlowProcess(QProcess):
            def start(self, program, arguments):
                super().start('/usr/bin/python3',['-c','import time; time.sleep(5)'])
        with patch.object(health_monitor,'QProcess',SlowProcess), patch.object(health_monitor,'PROBE_TIMEOUT_MS',80):
            monitor=health_monitor.HealthMonitor([],lambda age:(True,''))
            monitor.timer.stop();self.addCleanup(monitor.stop)
            ticks=[];timer=QTimer();timer.setInterval(10);timer.timeout.connect(lambda:ticks.append(1));timer.start()
            monitor.check();self.assertEqual(len(monitor._processes),2)
            monitor.check();self.assertEqual(len(monitor._processes),2)
            QTest.qWait(200)
            self.assertGreater(len(ticks),3)
            self.assertFalse(monitor._processes)
            self.assertEqual(monitor.state.failures['share'],1)
            monitor.check();QTest.qWait(200)
            self.assertIn('share',monitor.state.issues)
            timer.stop()


if __name__=='__main__':unittest.main()
