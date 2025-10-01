"""Utility for retrieving current weather conditions from OpenWeather."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional, Tuple
from urllib.parse import urlencode

from PyQt6.QtCore import QObject, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest


OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"


@dataclass
class WeatherSummary:
    """Parsed subset of data returned from the weather provider."""

    condition: Optional[str]
    temperature: Optional[float]
    feels_like: Optional[float]
    humidity: Optional[float]
    wind_speed: Optional[float]
    wind_direction: Optional[float]
    sunrise: Optional[int]
    sunset: Optional[int]
    timezone_offset: Optional[int]
    city: Optional[str]
    region: Optional[str]
    country: Optional[str]
    icon: Optional[str]

    def as_dict(self) -> dict:
        return {
            "condition": self.condition,
            "temperature": self.temperature,
            "feels_like": self.feels_like,
            "humidity": self.humidity,
            "wind_speed": self.wind_speed,
            "wind_direction": self.wind_direction,
            "sunrise": self.sunrise,
            "sunset": self.sunset,
            "timezone_offset": self.timezone_offset,
            "city": self.city,
            "region": self.region,
            "country": self.country,
            "icon": self.icon,
        }


class WeatherClient(QObject):
    """Fetches weather data asynchronously using ``QNetworkAccessManager``."""

    weatherFetched = pyqtSignal(dict)
    weatherError = pyqtSignal(str)

    def __init__(
        self,
        api_key: str,
        location: str,
        units: str = "metric",
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.api_key = (api_key or "").strip()
        self.location = (location or "").strip()
        self.units = (units or "metric").strip() or "metric"
        self._network = QNetworkAccessManager(self)
        self._pending_reply: Optional[QNetworkReply] = None

    def fetch_weather(self) -> None:
        """Trigger a weather request if configuration appears valid."""

        if not self.api_key or not self.location:
            self.weatherError.emit("Weather configuration is incomplete.")
            return

        request_url = self._build_request_url()
        if request_url is None:
            self.weatherError.emit("Unable to parse weather location.")
            return

        if self._pending_reply is not None:
            try:
                self._pending_reply.finished.disconnect(self._on_reply_finished)  # type: ignore[arg-type]
            except TypeError:
                pass
            self._pending_reply.abort()
            self._pending_reply.deleteLater()
            self._pending_reply = None

        request = QNetworkRequest(request_url)
        self._pending_reply = self._network.get(request)
        self._pending_reply.finished.connect(self._on_reply_finished)  # type: ignore[arg-type]

    def _on_reply_finished(self) -> None:
        reply_object = self.sender()
        if not isinstance(reply_object, QNetworkReply):
            return

        if reply_object is self._pending_reply:
            self._pending_reply = None

        reply_object.deleteLater()

        if reply_object.error() != QNetworkReply.NetworkError.NoError:
            self.weatherError.emit(reply_object.errorString())
            return

        try:
            payload = json.loads(bytes(reply_object.readAll()).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.weatherError.emit(f"Invalid weather response: {exc}")
            return

        summary = self._parse_summary(payload)
        if summary is None:
            self.weatherError.emit("Weather response missing expected fields.")
            return

        self.weatherFetched.emit(summary.as_dict())

    def _build_request_url(self) -> Optional[QUrl]:
        params = {
            "appid": self.api_key,
            "units": self.units or "metric",
        }

        coordinates = self._parse_coordinates(self.location)
        if coordinates is not None:
            lat, lon = coordinates
            params["lat"] = f"{lat:.6f}"
            params["lon"] = f"{lon:.6f}"
        else:
            params["q"] = self.location

        query = urlencode(params)
        url = QUrl(f"{OPENWEATHER_URL}?{query}")
        if not url.isValid():
            return None
        return url

    @staticmethod
    def _parse_coordinates(location: str) -> Optional[Tuple[float, float]]:
        pieces = [piece.strip() for piece in location.split(",")]
        if len(pieces) != 2:
            return None
        try:
            lat = float(pieces[0])
            lon = float(pieces[1])
        except ValueError:
            return None
        return lat, lon

    @staticmethod
    def _parse_summary(payload: dict) -> Optional[WeatherSummary]:
        weather_list = payload.get("weather")
        if isinstance(weather_list, list) and weather_list:
            weather_entry = weather_list[0]
            condition = weather_entry.get("description")
            icon = weather_entry.get("icon")
        else:
            condition = None
            icon = None

        main_section = payload.get("main")
        temperature = None
        feels_like = None
        humidity = None
        if isinstance(main_section, dict):
            temp_val = main_section.get("temp")
            if isinstance(temp_val, (int, float)):
                temperature = float(temp_val)
            feels_like_val = main_section.get("feels_like")
            if isinstance(feels_like_val, (int, float)):
                feels_like = float(feels_like_val)
            humidity_val = main_section.get("humidity")
            if isinstance(humidity_val, (int, float)):
                humidity = float(humidity_val)

        wind_section = payload.get("wind")
        wind_speed = None
        wind_direction = None
        if isinstance(wind_section, dict):
            speed_val = wind_section.get("speed")
            if isinstance(speed_val, (int, float)):
                wind_speed = float(speed_val)
            deg_val = wind_section.get("deg")
            if isinstance(deg_val, (int, float)):
                wind_direction = float(deg_val)

        sys_section = payload.get("sys")
        sunrise = None
        sunset = None
        country = None
        region = None
        if isinstance(sys_section, dict):
            sunrise_val = sys_section.get("sunrise")
            if isinstance(sunrise_val, int):
                sunrise = sunrise_val
            sunset_val = sys_section.get("sunset")
            if isinstance(sunset_val, int):
                sunset = sunset_val
            country_val = sys_section.get("country")
            if isinstance(country_val, str):
                country = country_val.strip()
            region_val = sys_section.get("state")
            if isinstance(region_val, str):
                region = region_val.strip()

        city = payload.get("name")
        if isinstance(city, str):
            city = city.strip()
        else:
            city = None

        timezone_offset = payload.get("timezone")
        if not isinstance(timezone_offset, int):
            timezone_offset = None

        return WeatherSummary(
            condition=condition,
            temperature=temperature,
            feels_like=feels_like,
            humidity=humidity,
            wind_speed=wind_speed,
            wind_direction=wind_direction,
            sunrise=sunrise,
            sunset=sunset,
            timezone_offset=timezone_offset,
            city=city,
            region=region,
            country=country,
            icon=icon,
        )

