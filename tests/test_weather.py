"""NWS conversion, lifecycle, overlay, and local solar regression tests."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtCore import QByteArray, QObject
from PyQt6.QtGui import QImage
from PyQt6.QtNetwork import QNetworkReply
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication
from slideshow.slideshow_manager import SlideshowManager
from utils import weather_client
from utils.solar import solar_times, MEDFORD_TIMEZONE

APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


def observation():
    def q(value, unit): return {"value": value, "unitCode": "wmoUnit:" + unit}
    return {"properties": {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "textDescription": "Clear", "temperature": q(23, "degC"),
        "heatIndex": q(None, "degC"), "windChill": q(20, "degC"),
        "relativeHumidity": q(42, "percent"), "windSpeed": q(16.09344, "km_h-1"),
        "windDirection": q(360, "degree_(angle)"), "icon": None,
    }}


class Reply(QNetworkReply):
    def __init__(self, payload=None, failed=False):
        super().__init__()
        self.payload = QByteArray(json.dumps(payload).encode())
        self.failed = failed
        self.aborted = False
    def error(self):
        return self.NetworkError.ConnectionRefusedError if self.failed else self.NetworkError.NoError
    def readAll(self): return self.payload
    def abort(self):
        self.aborted = True
        self.finished.emit()


class WeatherTests(unittest.TestCase):
    def test_mapping_and_unit_conversions(self):
        result = weather_client.WeatherClient._parse_summary(observation())
        self.assertAlmostEqual(result['temperature'], 73.4)
        self.assertAlmostEqual(result['feels_like'], 68)
        self.assertAlmostEqual(result['wind_speed'], 10)
        self.assertEqual(result['wind_direction'], 0)
        self.assertEqual(result['humidity'], 42)
        self.assertEqual(result['city'], 'Medford Airport')
        for unit,value,expected in [('degF',78,78),('K',273.15,32)]:
            self.assertAlmostEqual(weather_client.WeatherClient._quantity({'t':{'value':value,'unitCode':'wmoUnit:'+unit}},'t','temperature'), expected)
        for unit,value,expected in [('m_s-1',1,2.2369362921),('mi_h-1',10,10),('kn',10,11.50779448)]:
            self.assertAlmostEqual(weather_client.WeatherClient._quantity({'w':{'value':value,'unitCode':'wmoUnit:'+unit}},'w','speed'), expected)

    def test_missing_and_invalid_data(self):
        p={'properties': {'timestamp': datetime.now(timezone.utc).isoformat()}}
        s=weather_client.WeatherClient._parse_summary(p)
        self.assertIsNone(s['temperature']); self.assertIsNone(s['feels_like'])
        for bad in [None, [], {}, {'properties':{}}, {'properties':{'timestamp':'bad'}}, {'properties':{'timestamp':'2026-10-15T12:00:00'}}]:
            self.assertIsNone(weather_client.WeatherClient._parse_summary(bad))
        for value,unit in [(None,'degC'),(True,'degC'),(float('nan'),'degC'),(22,'unknown'),(22,None)]:
            self.assertIsNone(weather_client.WeatherClient._quantity({'t':{'value':value,'unitCode':unit}},'t','temperature'))

    def test_request_headers_success_failure_timeout(self):
        client=weather_client.WeatherClient()
        success=[]; errors=[]
        client.weatherFetched.connect(success.append); client.weatherError.connect(errors.append)
        class Network:
            def get(self, request):
                self.request=request; self.reply=Reply(observation()); return self.reply
        network=Network(); client._network=network
        client.fetch_weather()
        self.assertIn('KMFR/observations/latest',network.request.url().toString())
        self.assertTrue(bytes(network.request.rawHeader(b'User-Agent')))
        network.reply.finished.emit()
        self.assertEqual(len(success),1); self.assertIn('fetched_at',success[0]); self.assertFalse(client._timeout.isActive())
        client.fetch_weather(); network.reply.failed=True; network.reply.finished.emit()
        self.assertEqual(len(errors),1)
        client.fetch_weather(); network.reply.payload=QByteArray(b'not JSON'); network.reply.finished.emit()
        self.assertEqual(len(errors),2)
        with patch.object(weather_client,'REQUEST_TIMEOUT_MS',10):
            client.fetch_weather(); timed=network.reply; QTest.qWait(30)
        self.assertTrue(timed.aborted); self.assertIsNone(client._pending_reply)
        self.assertEqual(len(errors),3); self.assertIn('timed out',errors[-1])
        client.cancel()

    def test_overlay_staleness_retry_and_midnight(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'photo.png'; im=QImage(10,10,QImage.Format.Format_RGB32); im.fill(0); im.save(str(path))
            manager=SlideshowManager([d],image_paths=[str(path)],motion_enabled=False)
            manager.show(); APP.processEvents()
            with patch.object(weather_client.WeatherClient,'fetch_weather'):
                manager._initialize_weather('ignored','ignored','metric')
            s=weather_client.WeatherClient._parse_summary(observation())
            manager._on_weather_success(s)
            v=manager.viewer
            self.assertTrue(v.weather_container.isVisible())
            self.assertEqual(v.weather_location_label.text(),'Medford Airport')
            self.assertEqual(v.weather_temperature_label.text(),'73°F')
            self.assertEqual(v.weather_condition_label.text(),'Clear')
            self.assertIn('Observed',v.weather_updated_label.text()); self.assertIn('Fetched',v.weather_updated_label.text())
            self.assertTrue(v._sunrise_sunset_text)
            self.assertEqual(manager.weather_timer.interval(),300000)
            for delay in [600000,1200000,2400000,3600000,3600000]:
                manager._on_weather_error('NWS request failed')
                self.assertEqual(manager.weather_timer.interval(),delay)
                self.assertIn('STALE',v.weather_updated_label.text())
                self.assertEqual(v.weather_temperature_label.text(),'73°F')
                self.assertTrue(v._sunrise_sunset_text)
            manager._on_weather_success(s)
            self.assertNotIn('STALE',v.weather_updated_label.text()); self.assertEqual(manager.weather_timer.interval(),300000)
            s['observed_at']=(datetime.now(timezone.utc)-timedelta(hours=2)).isoformat()
            manager._on_weather_success(s); self.assertIn('STALE',v.weather_updated_label.text())
            manager._solar_date=date(2000,1,1)
            manager._refresh_weather_overlay()
            self.assertEqual(manager._solar_date,datetime.now(MEDFORD_TIMEZONE).date())
            self.assertEqual(manager._solar_events,solar_times(manager._solar_date))
            manager._latest_weather_summary=None; manager._weather_last_success=None; manager._on_weather_error('failure')
            self.assertIn('unavailable',v.weather_temperature_label.text())
            self.assertIn('STALE',v.weather_updated_label.text()); self.assertTrue(v._sunrise_sunset_text)
            manager.close()

    def test_solar_seasons_dst_and_local_date(self):
        for day,offset in [(date(2026,1,15),-8),(date(2026,7,15),-7),(date(2026,3,8),-7),(date(2026,11,1),-8)]:
            events=solar_times(day)
            rise=datetime.fromtimestamp(events['sunrise'],MEDFORD_TIMEZONE)
            setting=datetime.fromtimestamp(events['sunset'],MEDFORD_TIMEZONE)
            self.assertEqual(rise.date(),day); self.assertEqual(setting.date(),day)
            self.assertEqual(rise.utcoffset().total_seconds()/3600,offset)
            self.assertLess(rise,setting); self.assertTrue(5<=rise.hour<=8); self.assertTrue(16<=setting.hour<=21)
        # USNO independently reports 07:25 / 18:29 PDT for KMFR on this date.
        events = solar_times(date(2026, 10, 15))
        for key, hour, minute in [("sunrise", 7, 25), ("sunset", 18, 29)]:
            reference = datetime(2026, 10, 15, hour, minute, tzinfo=MEDFORD_TIMEZONE)
            self.assertLess(abs(events[key] - reference.timestamp()), 60)
        # DST changes the clock hour without shifting the physical event by an hour.
        for before,after in [(date(2026,3,7),date(2026,3,8)),(date(2026,10,31),date(2026,11,1))]:
            self.assertLess(abs(solar_times(after)['sunrise']-solar_times(before)['sunrise']-86400),180)

if __name__=='__main__': unittest.main()
