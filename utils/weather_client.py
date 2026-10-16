"""Asynchronous NWS observations for Medford Airport; no API key required."""
import json
import math
from datetime import datetime, timezone

from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

NWS_URL = "https://api.weather.gov/stations/KMFR/observations/latest"
USER_AGENT = b"Pi5-Photo-Viewer/1.0 (Medford Airport KMFR weather display)"
REQUEST_TIMEOUT_MS = 20000


class WeatherClient(QObject):
    weatherFetched = pyqtSignal(dict)
    weatherError = pyqtSignal(str)

    def __init__(self, api_key="", location="", units="imperial", parent=None):
        # Legacy arguments remain accepted; saved OpenWeather preferences are untouched.
        super().__init__(parent)
        self._network = QNetworkAccessManager(self)
        self._pending_reply = None
        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.timeout.connect(self._on_timeout)

    def fetch_weather(self):
        if self._pending_reply is not None:
            return
        request = QNetworkRequest(QUrl(NWS_URL))
        request.setRawHeader(b"User-Agent", USER_AGENT)
        request.setRawHeader(b"Accept", b"application/geo+json")
        self._pending_reply = self._network.get(request)
        self._pending_reply.finished.connect(self._on_reply_finished)
        self._timeout.start(REQUEST_TIMEOUT_MS)

    def cancel(self):
        self._timeout.stop()
        reply, self._pending_reply = self._pending_reply, None
        if reply is not None:
            reply.finished.disconnect(self._on_reply_finished)
            reply.abort()
            reply.deleteLater()

    def _on_timeout(self):
        self.cancel()
        self.weatherError.emit("NWS request timed out")

    def _on_reply_finished(self):
        reply = self.sender()
        if reply is not self._pending_reply:
            return
        self._pending_reply = None
        self._timeout.stop()
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                self.weatherError.emit("NWS request failed")
                return
            payload = json.loads(bytes(reply.readAll()).decode("utf-8"))
            summary = self._parse_summary(payload)
            if summary is None:
                self.weatherError.emit("Invalid NWS observation")
                return
            summary["fetched_at"] = datetime.now(timezone.utc).isoformat()
            self.weatherFetched.emit(summary)
        except (UnicodeDecodeError, ValueError, TypeError):
            self.weatherError.emit("Invalid NWS response")
        finally:
            reply.deleteLater()

    @staticmethod
    def _quantity(properties, field, kind):
        quantity = properties.get(field)
        if not isinstance(quantity, dict):
            return None
        value = quantity.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return None
        unit_code = quantity.get("unitCode")
        if not isinstance(unit_code, str):
            return None
        if kind == "speed" and value < 0:
            return None
        unit = unit_code.split(":")[-1]
        conversions = {
            "temperature": {"degC": lambda x: x * 9 / 5 + 32, "degF": lambda x: x, "K": lambda x: (x - 273.15) * 9 / 5 + 32},
            "speed": {"km_h-1": lambda x: x / 1.609344, "m_s-1": lambda x: x * 2.2369362921, "mi_h-1": lambda x: x, "kn": lambda x: x * 1.150779448},
            "direction": {"degree_(angle)": lambda x: x % 360},
            "humidity": {"percent": lambda x: x if 0 <= x <= 100 else None},
        }
        convert = conversions[kind].get(unit)
        return convert(value) if convert else None

    @classmethod
    def _parse_summary(cls, payload):
        if not isinstance(payload, dict) or not isinstance(payload.get("properties"), dict):
            return None
        p = payload["properties"]
        if "timestamp" not in p:
            return None
        try:
            observed = datetime.fromisoformat(p["timestamp"].replace("Z", "+00:00"))
            if observed.tzinfo is None:
                return None
        except (ValueError, TypeError, AttributeError):
            return None
        feels_like = cls._quantity(p, "heatIndex", "temperature")
        if feels_like is None:
            feels_like = cls._quantity(p, "windChill", "temperature")
        condition = p.get("textDescription")
        icon = p.get("icon")
        return {
            "city": "Medford Airport", "region": None, "country": None,
            "condition": condition if isinstance(condition, str) else None,
            "temperature": cls._quantity(p, "temperature", "temperature"),
            "feels_like": feels_like,
            "humidity": cls._quantity(p, "relativeHumidity", "humidity"),
            "wind_speed": cls._quantity(p, "windSpeed", "speed"),
            "wind_direction": cls._quantity(p, "windDirection", "direction"),
            "observed_at": observed.isoformat(),
            "icon": icon if isinstance(icon, str) and icon.startswith("https://api.weather.gov/") else None,
        }
