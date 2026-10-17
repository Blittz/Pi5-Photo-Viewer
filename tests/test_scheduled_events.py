import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from datetime import datetime,timedelta,timezone,time
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PyQt6.QtCore import Qt,QEvent,QPointF
from PyQt6.QtGui import QFontMetrics,QMouseEvent,QCursor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication
from utils.scheduled_events import validate_snapshot,event_view,read_snapshot,STALE_AFTER,event_title
from utils.event_client import EventClient
from slideshow.slideshow_manager import SlideshowManager
from slideshow.health_indicator import event_color,warning_color

APP=QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)
NOW=datetime(2026,10,16,18,tzinfo=timezone.utc)


def event(eid='10',hours=2,status='scheduled',end=True,server='1'):
    start=NOW+timedelta(hours=hours)
    return {'id':eid,'server_id':server,'title':'Example adventure session','start_at':start.isoformat(),
            'end_at':(start+timedelta(hours=3)).isoformat() if end else None,
            'status':status,'kind':'external','channel_id':None}


def snapshot(events=None,now=NOW):
    return {'schema_version':1,'last_attempted_refresh':now.isoformat(),'last_successful_refresh':now.isoformat(),
            'refresh_ok':True,'servers':[{'id':'1','name':'Example server','refresh_ok':True,'last_successful_refresh':now.isoformat()}],
            'events':[event()] if events is None else events}


class EventModelTests(unittest.TestCase):
    def view(self,data,now=NOW,failed=False):return event_view(validate_snapshot(data),failed,now)

    def test_ordering_and_all_server_titles_without_keyword_filter(self):
        data=snapshot([event('11',5),event('10',2)])
        data['events'][1]['title']='Community art night'
        data['servers'].append({'id':'2','name':'Second server','refresh_ok':True,'last_successful_refresh':NOW.isoformat()})
        data['events'].append(event('12',1,server='2'))
        view=self.view(data)
        self.assertIn('Second server',view['detail']);self.assertIn('1h',view['detail'])
        data['events'].pop();self.assertEqual(self.view(data)['title'],'Community art night (Example server)')

    def test_title_server_display_name_and_missing_name(self):
        self.assertEqual(event_title('D&D Friday Session','Dnd 2024'), 'D&D Friday Session (Dnd 2024)')
        self.assertEqual(event_title('Session','𝒟&𝒟: 照片'), 'Session (𝒟&𝒟: 照片)')
        for name in (None,'','   '):self.assertEqual(event_title('Session',name),'Session')
        data=snapshot();data['servers'][0]['name']='Dnd 2024'
        self.assertEqual(self.view(data)['title'],'Example adventure session (Dnd 2024)')
        self.assertEqual(self.view(data,failed=True)['title'],'Example adventure session (Dnd 2024)')
        for name in (None, '', '   '):
            data['servers'][0]['name']=name
            self.assertEqual(self.view(data)['title'],'Example adventure session')
        data['servers'][0].pop('name')
        self.assertEqual(self.view(data)['title'],'Example adventure session')

    def test_24_hour_boundary_starting_grace_and_no_stuck_blue(self):
        for seconds,blue in [(86401,False),(86400,True),(1,True),(0,False),(-299,False)]:
            data=snapshot();data['events'][0]['start_at']=(NOW+timedelta(seconds=seconds)).isoformat()
            data['events'][0]['end_at']=None
            self.assertEqual(self.view(data)['imminent'],blue)
        data['events'][0]['start_at']=(NOW-timedelta(minutes=6)).isoformat()
        self.assertEqual(self.view(data)['title'],'No upcoming events')

    def test_active_completed_canceled_and_missing_end(self):
        for status in ('completed','canceled'):
            self.assertEqual(self.view(snapshot([event(status=status)]))['title'],'No upcoming events')
        early=snapshot([event(hours=1,status='active',end=False)])
        self.assertEqual(self.view(early)['heading'],'SESSION NOW')
        self.assertFalse(self.view(early)['imminent'])
        data=snapshot([event(hours=-1,status='active',end=False)])
        self.assertIn('In progress',self.view(data)['detail']);self.assertIn('End not listed',self.view(data)['detail'])
        self.assertFalse(self.view(data)['imminent'])
        data=snapshot([event(hours=-5,status='active',end=False)])
        self.assertEqual(self.view(data)['title'],'No upcoming events')
        data=snapshot([event(hours=-2,status='active')]);self.assertIn('In progress',self.view(data)['detail'])
        data=snapshot([event(hours=-4,status='active')]);self.assertEqual(self.view(data)['title'],'No upcoming events')

    def test_stale_failed_missing_and_empty_are_distinct(self):
        self.assertEqual(event_view(None,now=NOW)['title'],'Event data unavailable')
        data=snapshot([]);self.assertEqual(self.view(data)['title'],'No upcoming events')
        data['refresh_ok']=False;self.assertEqual(self.view(data)['title'],'Event data stale')
        data=snapshot();view=self.view(data,failed=True)
        self.assertEqual(view['heading'],'LAST KNOWN SESSION');self.assertIn('STALE',view['note']);self.assertFalse(view['imminent'])
        for age,stale in [(900,False),(901,True),(-301,True)]:
            data=snapshot(now=NOW-timedelta(seconds=age))
            self.assertEqual(self.view(data)['stale'],stale)

    def test_timezone_dst_and_local_date(self):
        for value,expected in [('2026-11-01T08:30:00+00:00','1:30 AM PDT'),
                               ('2026-11-01T09:30:00+00:00','1:30 AM PST'),
                               ('2026-03-08T10:30:00+00:00','3:30 AM PDT')]:
            start=datetime.fromisoformat(value);now=start-timedelta(hours=1)
            data=snapshot(now=now);data['events'][0]['start_at']=value;data['events'][0]['end_at']=None
            view=self.view(data,now)
            self.assertIn(expected,view['when']);self.assertIn('Sunday',view['when']);self.assertIn('1h',view['detail'])

    def test_validation_and_file_size_symlink_missing_data(self):
        for mutate in [lambda d:d.update(schema_version=2),lambda d:d['events'][0].update(start_at='2026-10-17T10:00:00'),
                       lambda d:d['events'][0].update(status='unknown'),lambda d:d['events'][0].update(channel_id='2')]:
            data=snapshot();mutate(data)
            with self.assertRaises((ValueError,KeyError)):validate_snapshot(data)
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'events.json'
            with self.assertRaises(OSError):read_snapshot(path)
            path.write_text('x'*300000)
            with self.assertRaises(ValueError):read_snapshot(path)
            path.write_text(json.dumps(snapshot()))
            link=Path(temp)/'link';link.symlink_to(path)
            with self.assertRaises(OSError):read_snapshot(link)
            self.assertEqual(read_snapshot(path)['events'][0]['title'],'Example adventure session')

    def test_rescheduling_and_terminal_status_replace_previous_choice(self):
        data=snapshot([event('10',1),event('11',3)])
        self.assertIn('1h',self.view(data)['detail'])
        data['events'][0]['start_at']=(NOW+timedelta(days=2)).isoformat();data['events'][0]['end_at']=None
        self.assertIn('3h',self.view(data)['detail'])
        data['events'][1]['status']='canceled';self.assertFalse(self.view(data)['imminent'])


class EventQtTests(unittest.TestCase):
    def manager(self):
        with patch('utils.weather_client.WeatherClient.fetch_weather'),patch('utils.health_monitor.HealthMonitor._start_probe'),patch.object(EventClient,'refresh'):
            manager=SlideshowManager([],image_paths=[],weather_enabled=True,weather_font_size=29,
                                     night_start='21:00',night_end='05:30',night_display_brightness=40)
            manager.resize(1920,1080);manager.show();APP.processEvents()
        manager.health_monitor.timer.stop();manager.event_client.timer.stop();manager.event_timer.stop()
        manager._on_weather_success({'condition':'Clear','temperature':65,'humidity':38,'wind_speed':4,
                                     'observed_at':datetime.now(timezone.utc).isoformat()})
        self.addCleanup(manager.close)
        return manager

    def test_red_priority_blue_restoration_and_night_dimming(self):
        manager=self.manager();manager.evaluate_night_mode(time(12))
        now=datetime.now(timezone.utc);data=snapshot(now=now);data['events'][0]['start_at']=(now+timedelta(hours=2)).isoformat();data['events'][0]['end_at']=None
        manager.event_client.snapshot=validate_snapshot(data);manager._refresh_event_view();APP.processEvents()
        self.assertEqual(manager.health_edge.mode,'event')
        expected = 'Example adventure session (Example server)'
        self.assertEqual(manager.viewer.sidebar.event_panel.title.text(), expected)
        self.assertEqual(manager.night_display.event_panel.title.text(), expected)
        self.assertEqual(manager.viewer.event_caption.title.text(), expected)
        for _ in range(2):manager.health_monitor.record('bot',False,'Photo bot service stopped')
        self.assertEqual(manager.health_edge.mode,'health')
        self.assertTrue(manager.viewer.sidebar.event_panel.isVisible())
        manager.health_monitor.record('bot',True);self.assertEqual(manager.health_edge.mode,'event')
        manager.evaluate_night_mode(time(22));APP.processEvents()
        self.assertEqual(manager.health_edge.brightness,40)
        self.assertLess(event_color(40).blue(),event_color().blue())
        manager.event_client.read_failed=True;manager._refresh_event_view()
        self.assertIsNone(manager.health_edge.mode);self.assertIn('STALE',manager.night_display.event_panel.note.text())

    def test_long_title_and_both_layouts_fit_without_smaller_weather(self):
        manager=self.manager();now=datetime.now(timezone.utc)
        data=snapshot(now=now);data['events'][0].update(title='A long adventure across the forgotten mountains with returning friends and a very unexpected visitor',start_at=(now+timedelta(hours=2)).isoformat(),end_at=None)
        manager.event_client.snapshot=validate_snapshot(data);manager._refresh_event_view()
        for night in (False,True):
            manager.evaluate_night_mode(time(22) if night else time(12));APP.processEvents();QTest.qWait(50)
            panel=manager.night_display if night else manager.viewer.sidebar
            self.assertEqual(panel.verticalScrollBar().maximum(),0)
            self.assertGreaterEqual(panel.condition_label.font().pixelSize(),46)
            self.assertTrue(panel.event_panel.title.wordWrap())
            for label in panel.event_panel.labels:
                if label.isVisible():self.assertGreaterEqual(label.height(),QFontMetrics(label.font()).height())
            manager.idle_cursor._hide_cursor();manager._refresh_event_view();APP.processEvents()
            self.assertTrue(manager.idle_cursor.hidden)

    def test_missing_conditions_long_title_stale_and_health_warning_fit(self):
        manager=self.manager();manager.evaluate_night_mode(time(12))
        manager._on_weather_success({'condition':None,'temperature':43,'humidity':61,'wind_speed':0,
                                     'wind_direction':0,'observed_at':datetime.now(timezone.utc).isoformat()})
        now=datetime.now(timezone.utc);data=snapshot(now=now)
        data['servers'][0]['name']='Example Adventure Server'
        data['events'][0].update(title='The forgotten mountains: an unexpected visitor returns for another adventure with old friends',
                                 start_at=(now+timedelta(hours=3)).isoformat(),end_at=None)
        manager.event_client.snapshot=validate_snapshot(data);manager.event_client.read_failed=True
        for _ in range(2):manager.health_monitor.record('bot',False,'Photo bot service stopped')
        manager._refresh_event_view();QTest.qWait(100)
        self.assertEqual(manager.viewer.sidebar.verticalScrollBar().maximum(),0)
        self.assertEqual(manager.health_edge.mode,'health')
        self.assertTrue(manager.viewer.sidebar.health_notice.isVisible())
        self.assertTrue(manager.viewer.sidebar.event_panel.note.isVisible())

    def test_stationary_synthetic_mouse_move_does_not_reveal_cursor(self):
        manager=self.manager();manager.idle_cursor._hide_cursor()
        target=manager.viewer.sidebar
        move=QMouseEvent(QEvent.Type.MouseMove,QPointF(10,10),QPointF(QCursor.pos()),
                         Qt.MouseButton.NoButton,Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier)
        APP.sendEvent(target,move)
        self.assertTrue(manager.idle_cursor.hidden)

    def test_reader_preserves_cache_on_corruption_and_recovers(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'events.json';data=snapshot(now=datetime.now(timezone.utc));path.write_text(json.dumps(data))
            client=EventClient(path=path);client.timer.stop();self.addCleanup(client.stop)
            def wait():
                for _ in range(100):
                    APP.processEvents();QTest.qWait(10)
                    if client.job is None:return
                self.fail('Event read did not finish')
            client.refresh();wait();self.assertIsNotNone(client.snapshot);self.assertFalse(client.read_failed)
            path.write_text('{corrupt');client.refresh();wait()
            self.assertTrue(client.read_failed);self.assertIsNotNone(client.snapshot)
            path.write_text(json.dumps(data));client.refresh();wait();self.assertFalse(client.read_failed)


if __name__=='__main__':unittest.main()
