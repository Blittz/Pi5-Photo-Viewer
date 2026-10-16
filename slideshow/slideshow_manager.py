import os
import random
from datetime import datetime, time as time_cls, timezone
from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import QWidget, QStackedLayout
from PyQt6.QtGui import QImageReader
from .image_viewer import ImageViewer, SUPPORTED_TRANSITIONS
from .idle_cursor import IdleCursor
from .health_indicator import HealthEdge
from utils.health_monitor import HealthMonitor
from utils.event_client import EventClient
from utils.scheduled_events import event_view
from .night_display import NightDisplay, DEFAULT_NIGHT_BRIGHTNESS
from utils.weather_client import WeatherClient
from utils.solar import MEDFORD_TIMEZONE, solar_times

SUPPORTED_IMAGE_FORMATS = ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp')

LEGACY_TRANSITION_ALIASES = {
    "slide": ["slide-horizontal", "slide-vertical"],
}


def get_all_images_from_folders(folders):
    image_paths = []
    for folder in folders:
        if not os.path.isdir(folder):
            continue
        for root, _, files in os.walk(folder):
            for file in sorted(files):
                if file.lower().endswith(SUPPORTED_IMAGE_FORMATS):
                    image_paths.append(os.path.join(root, file))
    return image_paths


class SlideshowManager(QWidget):
    weatherSummaryAvailable = pyqtSignal(bool, dict)

    def __init__(
        self,
        folders,
        shuffle=False,
        duration=5,
        motion_enabled=True,
        folder_font_size=24,
        date_font_size=20,
        weather_font_size=18,
        transitions=None,
        night_start=None,
        night_end=None,
        weather_enabled=False,
        weather_api_key="",
        weather_location="",
        weather_units="metric",
        image_paths=None,
        night_display_brightness=DEFAULT_NIGHT_BRIGHTNESS,
    ):
        super().__init__()

        self.folders = folders
        self.shuffle = shuffle
        self.duration = duration
        self.motion_enabled = motion_enabled
        self.folder_font_size = folder_font_size
        self.date_font_size = date_font_size
        self.weather_font_size = weather_font_size
        self.current_index = 0
        self.current_image_path = None
        self.images = []
        self.blackout_active = False
        self.night_start = self._parse_time(night_start)
        self.night_end = self._parse_time(night_end)
        self.weather_enabled = bool(weather_enabled)
        self.weather_client = None
        self.weather_timer = None
        self._weather_refresh_interval_ms = 5 * 60 * 1000  # 5 minutes
        self._latest_weather_summary = None
        self._weather_last_success = None
        self._weather_units = "imperial"
        self._weather_failures = 0
        self._weather_error = None
        self._solar_date = None
        self._solar_events = {}
        if transitions is None:
            self.transitions = list(SUPPORTED_TRANSITIONS)
        else:
            self.transitions = self._normalize_transitions(transitions)

        self.viewer = ImageViewer(
            motion_enabled=self.motion_enabled,
            folder_font_size=self.folder_font_size,
            date_font_size=self.date_font_size,
            weather_font_size=self.weather_font_size,
        )
        self.viewer.set_available_transitions(self.transitions)
        self.viewer.set_weather_overlay(None)
        self.viewer.set_metadata_font_sizes(
            self.folder_font_size, self.date_font_size
        )
        self.viewer.set_weather_font_size(self.weather_font_size)

        self.night_display = NightDisplay(self, font_size=self.weather_font_size,
                                          brightness=night_display_brightness)
        layout = QStackedLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.viewer)
        layout.addWidget(self.night_display)
        self.display_stack = layout
        self.setLayout(layout)
        self.health_edge = HealthEdge(self)
        self.health_edge.setGeometry(self.rect())

        # Enable the slideshow window to receive keyboard focus so it can
        # react to shortcut keys such as Escape and F11.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Timer to switch images
        self.slideshow_timer = QTimer(self)
        self.slideshow_timer.timeout.connect(self.next_image)

        # Timer to refresh folder images
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_images)

        # Timer to monitor night schedule
        self.idle_cursor = IdleCursor(self)

        self.night_timer = QTimer(self)
        self.night_timer.timeout.connect(self.evaluate_night_mode)
        self.weather_status_timer = QTimer(self)
        self.weather_status_timer.setInterval(60000)
        self.weather_status_timer.timeout.connect(self._refresh_weather_overlay)
        self.weather_status_timer.start()

        if image_paths is None:
            self.load_images()
        else:
            self.images = list(image_paths)
            if self.shuffle:
                random.shuffle(self.images)
        self.start_slideshow()

        self.slideshow_timer.start(self.duration * 1000)
        self.refresh_timer.start(60000)  # 60 seconds
        if self.night_start is not None and self.night_end is not None:
            self.night_timer.start(60000)  # 60 seconds
        else:
            self.night_timer.stop()
        self.evaluate_night_mode()

        if weather_enabled:
            self._initialize_weather(
                api_key=weather_api_key,
                location=weather_location,
                units=weather_units,
            )
        else:
            self._refresh_weather_overlay()

        self.health_monitor = HealthMonitor(self.folders, self._health_weather_check, self)
        self.health_monitor.issuesChanged.connect(self._apply_health_issues)
        self.event_client = EventClient(self)
        self.event_client.changed.connect(self._refresh_event_view)
        self.event_timer = QTimer(self)
        self.event_timer.setInterval(5000)
        self.event_timer.timeout.connect(self._refresh_event_view)
        self.event_timer.start()
        self._refresh_event_view()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "health_edge"):
            self.health_edge.setGeometry(self.rect())
            self.health_edge.raise_()

    def _apply_health_issues(self, issues):
        self.viewer.sidebar.set_health_issues(issues)
        self.night_display.set_health_issues(issues)
        brightness = self.night_display.brightness if self.blackout_active else None
        imminent = getattr(self, "_event_view", {}).get("imminent", False)
        self.health_edge.set_health(issues, brightness, imminent=imminent)
        self.viewer.set_event_caption(self._event_view if imminent and not self.blackout_active else None)

    def _refresh_event_view(self):
        if not hasattr(self, "event_client"):
            return
        view = event_view(self.event_client.snapshot, self.event_client.read_failed)
        if view != getattr(self, "_event_view", None):
            self._event_view = view
            self.viewer.sidebar.set_event_view(view)
            self.night_display.set_event_view(view)
            self._refresh_health_indicator()

    def _refresh_health_indicator(self):
        if hasattr(self, "health_monitor"):
            self._apply_health_issues(self.health_monitor.state.messages())

    def _health_weather_check(self, startup_age):
        if not self.weather_enabled:
            return True, ""
        if not self._latest_weather_summary:
            if self._weather_error or startup_age >= 90:
                return False, "Weather unavailable"
            return None, ""
        if self._weather_is_stale(self._latest_weather_summary):
            return False, "Weather stale"
        return True, ""

    def load_images(self):
        self.images = get_all_images_from_folders(self.folders)
        if self.shuffle:
            random.shuffle(self.images)

    def refresh_images(self):
        new_images = get_all_images_from_folders(self.folders)

        if self.shuffle:
            random.shuffle(new_images)

        # Attempt to maintain current image
        if self.current_image_path in new_images:
            self.current_index = new_images.index(self.current_image_path)
        else:
            self.current_index = 0
            self.current_image_path = None

        self.images = new_images

    def start_slideshow(self):
        if not self.images:
            return
        self.show_image(self.current_index)

    def show_image(self, index):
        if not self.images or self.blackout_active:
            return
        # Files can be corrupt or disappear after the startup validation.
        # Skip them without presenting an empty image or looping forever.
        index %= len(self.images)
        while self.images and QImageReader(self.images[index]).read().isNull():
            self.images.pop(index)
            if self.images:
                index %= len(self.images)
        if not self.images:
            return
        previous_path = self.current_image_path
        self.current_index = index % len(self.images)
        self.current_image_path = self.images[self.current_index]
        transition = None
        if previous_path and self.transitions:
            transition = random.choice(self.transitions)
        self.viewer.set_image(
            self.current_image_path,
            duration=self.duration,
            transition=transition,
        )

    def next_image(self):
        if not self.images or self.blackout_active:
            return
        self.current_index = (self.current_index + 1) % len(self.images)
        self.show_image(self.current_index)

    def pause(self):
        self.slideshow_timer.stop()

    def resume(self):
        if not self.blackout_active:
            self.slideshow_timer.start(self.duration * 1000)

    def set_duration(self, seconds):
        self.duration = seconds
        if not self.blackout_active:
            self.slideshow_timer.start(self.duration * 1000)

    def toggle_shuffle(self, enabled):
        self.shuffle = enabled
        self.load_images()
        self.current_index = 0
        self.start_slideshow()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
            return
        if event.key() == Qt.Key.Key_F11:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        # Stop timers when the slideshow window closes to ensure there are no
        # lingering updates running in the background.
        self.health_monitor.stop()
        self.event_client.stop()
        self.event_timer.stop()
        self.idle_cursor.stop()
        self.slideshow_timer.stop()
        self.refresh_timer.stop()
        self.night_timer.stop()
        if self.weather_timer is not None:
            self.weather_timer.stop()
        if self.weather_client is not None:
            self.weather_client.cancel()
        if hasattr(self, "weather_status_timer"):
            self.weather_status_timer.stop()
        self.night_display.clock_timer.stop()
        super().closeEvent(event)

    def _initialize_weather(self, api_key, location, units):
        self.weather_enabled = True
        self._weather_units = "imperial"
        self.weather_client = WeatherClient(parent=self)
        self.weather_client.weatherFetched.connect(self._on_weather_success)
        self.weather_client.weatherError.connect(self._on_weather_error)
        self.weather_timer = QTimer(self)
        self.weather_timer.setSingleShot(True)
        self.weather_timer.timeout.connect(self._request_weather_update)
        self._refresh_weather_overlay()
        self._request_weather_update()

    def _request_weather_update(self):
        if self.weather_client is not None:
            self.weather_client.fetch_weather()

    def _on_weather_success(self, payload):
        self._latest_weather_summary = payload
        self._weather_last_success = datetime.now(timezone.utc)
        self._weather_failures = 0
        self._weather_error = None
        self.weather_timer.start(self._weather_refresh_interval_ms)
        self._refresh_weather_overlay()
        self.weatherSummaryAvailable.emit(True, payload)

    def _on_weather_error(self, message):
        self._weather_failures = min(self._weather_failures + 1, 4)
        self._weather_error = message
        # Retry after 10, 20, 40, then 60 minutes; success restores five minutes.
        delay = min(self._weather_refresh_interval_ms * 2 ** self._weather_failures, 60 * 60 * 1000)
        self.weather_timer.start(delay)
        self._refresh_weather_overlay()
        self.weatherSummaryAvailable.emit(False, {"error": message})

    def _refresh_weather_overlay(self):
        now = datetime.now(MEDFORD_TIMEZONE)
        if now.date() != self._solar_date:
            self._solar_date = now.date()
            self._solar_events = solar_times(self._solar_date)
        payload = dict(self._latest_weather_summary or {"city": "Medford Airport"})
        payload.update(self._solar_events)
        text = self._format_weather_text(payload, self._weather_last_success)
        overlay = {"text": text, "icon": payload.get("icon"), "summary": payload}
        self.viewer.set_weather_overlay(overlay if self.weather_enabled else None)
        lines = (text.split("\n") + [""] * 7)[:7]
        if not self.weather_enabled:
            lines[2] = "Weather disabled"
            lines[6] = "Local solar times · America/Los_Angeles"
        self.night_display.set_weather(lines, payload, payload.get("icon"))
        # Let wrapped labels settle before measuring the optional warning row.
        # This also removes a startup scrollbar after the first weather response.
        QTimer.singleShot(0, self._refresh_health_indicator)

    def _weather_is_stale(self, payload, now=None):
        now = now or datetime.now(timezone.utc)
        try:
            age = (now - datetime.fromisoformat(payload.get("observed_at"))).total_seconds()
        except (ValueError, TypeError):
            return True
        return bool(self._weather_error) or age > 90 * 60 or age < -5 * 60

    def _weather_status_text(self, payload, now=None):
        now = now or datetime.now(timezone.utc)
        observed = payload.get("observed_at")
        try:
            observation = datetime.fromisoformat(observed)
            age = (now - observation).total_seconds()
        except (ValueError, TypeError):
            observation, age = None, None
        stale = self._weather_is_stale(payload, now)
        status = "STALE — " if stale else ""
        if observation is not None:
            status += "Observed " + observation.astimezone(MEDFORD_TIMEZONE).strftime("%b %d %I:%M %p %Z")
        else:
            status += "Observation unavailable"
        if self._weather_last_success is not None:
            status += " · Fetched " + self._weather_last_success.astimezone(MEDFORD_TIMEZONE).strftime("%b %d %I:%M %p %Z")
        if self._weather_error:
            status += " · Update failed; retry in " + str(self.weather_timer.interval() // 60000) + " min"
        return status

    def _format_weather_text(self, payload, timestamp):
        if not isinstance(payload, dict):
            return str(payload)

        lines = [""] * 7

        location_line = self._format_location_line(payload)
        if location_line:
            lines[0] = location_line

        temperature_line = self._format_temperature_line(payload)
        if temperature_line:
            lines[1] = temperature_line

        if not temperature_line:
            lines[1] = "Temperature unavailable"

        summary_line = self._format_condition_line(payload)
        if summary_line:
            lines[2] = summary_line

        if not summary_line:
            lines[2] = "Conditions unavailable"

        feels_like_line = self._format_feels_like_line(payload)
        if feels_like_line:
            lines[3] = feels_like_line

        humidity_line = self._format_humidity_line(payload)
        wind_line = self._format_wind_line(payload)

        if humidity_line and wind_line:
            lines[4] = f"{humidity_line}   {wind_line}"
        elif humidity_line or wind_line:
            lines[4] = humidity_line or wind_line

        sun_line = self._format_solar_line(payload)
        if sun_line:
            lines[5] = sun_line

        lines[6] = self._weather_status_text(payload)

        # Remove trailing empty lines while preserving positional blanks in between entries.
        while lines and lines[-1] == "":
            lines.pop()

        return "\n".join(lines)

    def _format_temperature(self, value):
        if value is None:
            return ""

        unit = self._weather_units.lower()
        if unit == "imperial":
            temp_f = value
        elif unit == "metric":
            temp_f = (value * 9.0 / 5.0) + 32.0
        elif unit == "standard":
            temp_f = ((value - 273.15) * 9.0 / 5.0) + 32.0
        else:
            temp_f = value
        return f"{temp_f:.0f}°F"

    def _format_temperature_line(self, payload):
        temperature = payload.get("temperature")
        if isinstance(temperature, (int, float)):
            return self._format_temperature(float(temperature))
        return ""

    def _format_feels_like_line(self, payload):
        feels_like = payload.get("feels_like")
        if isinstance(feels_like, (int, float)):
            formatted = self._format_temperature(float(feels_like))
            if formatted:
                return f"Feels like {formatted}"
        return ""

    @staticmethod
    def _format_condition_line(payload):
        condition = payload.get("condition")
        if isinstance(condition, str):
            text = condition.strip()
            if text:
                return text.title()
        return ""

    @staticmethod
    def _format_humidity_line(payload):
        humidity = payload.get("humidity")
        if isinstance(humidity, (int, float)):
            return f"💧 {humidity:.0f}%"
        return ""

    def _format_wind_line(self, payload):
        speed = payload.get("wind_speed")
        direction = payload.get("wind_direction")

        formatted_speed = ""
        if isinstance(speed, (int, float)):
            formatted_speed = self._format_wind_speed(float(speed))

        formatted_direction = ""
        if isinstance(direction, (int, float)):
            formatted_direction = self._format_wind_direction(float(direction))

        if not formatted_speed and not formatted_direction:
            return ""

        if formatted_speed and formatted_direction:
            return f"🌬️ {formatted_speed} ({formatted_direction})"
        if formatted_speed:
            return f"🌬️ {formatted_speed}"
        return f"🌬️ {formatted_direction}"

    def _format_wind_speed(self, value):
        unit = self._weather_units.lower()
        if unit == "imperial":
            mph = value
        else:
            # OpenWeather returns meters per second for metric/standard units.
            mph = value * 2.23694
        return f"{mph:.0f} mph"

    @staticmethod
    def _format_wind_direction(value):
        directions = [
            "N",
            "NNE",
            "NE",
            "ENE",
            "E",
            "ESE",
            "SE",
            "SSE",
            "S",
            "SSW",
            "SW",
            "WSW",
            "W",
            "WNW",
            "NW",
            "NNW",
        ]
        index = int((value % 360) / 22.5 + 0.5) % len(directions)
        return directions[index]

    def _format_solar_line(self, payload):
        sunrise = payload.get("sunrise")
        sunset = payload.get("sunset")
        timezone_offset = payload.get("timezone_offset")

        sunrise_text = (
            self._format_solar_time(int(sunrise), timezone_offset)
            if isinstance(sunrise, int)
            else ""
        )
        sunset_text = (
            self._format_solar_time(int(sunset), timezone_offset)
            if isinstance(sunset, int)
            else ""
        )

        if not sunrise_text and not sunset_text:
            return ""

        if sunrise_text and sunset_text:
            return f"🌅 {sunrise_text}  🌇 {sunset_text}"
        if sunrise_text:
            return f"🌅 {sunrise_text}"
        return f"🌇 {sunset_text}"

    def _format_solar_time(self, timestamp_value, timezone_offset):
        return self._format_time(datetime.fromtimestamp(timestamp_value, MEDFORD_TIMEZONE))

    def _format_location_line(self, payload):
        city = payload.get("city") or payload.get("name")
        region = payload.get("region")
        country = payload.get("country")
        parts = []
        if isinstance(city, str) and city.strip():
            parts.append(city.strip())

        region_text = ""
        if isinstance(region, str) and region.strip():
            region_text = region.strip()
        elif isinstance(country, str) and country.strip():
            region_text = country.strip()

        if region_text:
            parts.append(region_text)

        if not parts:
            return ""

        return ", ".join(parts)

    @staticmethod
    def _format_time(timestamp):
        formatted = timestamp.strftime("%I:%M %p")
        return formatted.lstrip("0")

    def evaluate_night_mode(self, current_time=None):
        if self.night_start is None or self.night_end is None:
            if self.blackout_active:
                self._exit_blackout_state()
            return

        now = datetime.now(MEDFORD_TIMEZONE).time() if current_time is None else current_time
        if self._is_within_blackout(now):
            self._enter_blackout_state()
        else:
            self._exit_blackout_state()

    def _enter_blackout_state(self):
        if self.blackout_active:
            return
        self.blackout_active = True
        self.slideshow_timer.stop()
        self.viewer.show_black_screen()
        self.display_stack.setCurrentWidget(self.night_display)
        self._refresh_weather_overlay()
        if hasattr(self, "health_monitor"):
            self._apply_health_issues(self.health_monitor.state.messages())

    def _exit_blackout_state(self):
        if not self.blackout_active:
            return
        self.blackout_active = False
        self.display_stack.setCurrentWidget(self.viewer)
        if hasattr(self, "health_monitor"):
            self._apply_health_issues(self.health_monitor.state.messages())
        if self.images:
            self.show_image(self.current_index)
        self.slideshow_timer.start(self.duration * 1000)

    @staticmethod
    def _normalize_transitions(transitions):
        if not transitions:
            return []

        if isinstance(transitions, str):
            transitions = [transitions]

        supported_set = set(SUPPORTED_TRANSITIONS)
        normalized = []
        for transition in transitions:
            if not isinstance(transition, str):
                continue
            transition = transition.strip().lower()
            if transition in supported_set:
                if transition not in normalized:
                    normalized.append(transition)
            elif transition in LEGACY_TRANSITION_ALIASES:
                for alias in LEGACY_TRANSITION_ALIASES[transition]:
                    if alias in supported_set and alias not in normalized:
                        normalized.append(alias)
        return normalized

    @staticmethod
    def _parse_time(value):
        if isinstance(value, time_cls):
            return value
        if isinstance(value, str):
            try:
                hour, minute = value.split(":", 1)
                return time_cls(int(hour), int(minute))
            except (ValueError, TypeError):
                return None
        return None

    def _is_within_blackout(self, current_time):
        start = self.night_start
        end = self.night_end

        if start is None or end is None:
            return False

        if start == end:
            return False

        if start < end:
            return start <= current_time < end
        return current_time >= start or current_time < end
