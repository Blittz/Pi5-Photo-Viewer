"""Local sunrise/sunset using NOAA solar equations (standard 90.833° zenith).

https://gml.noaa.gov/grad/solcalc/solareqns.PDF
Times are approximate: terrain and atmospheric conditions are not modeled.
"""
import math
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

MEDFORD_LATITUDE = 42.37503
MEDFORD_LONGITUDE = -122.87696
MEDFORD_TIMEZONE = ZoneInfo("America/Los_Angeles")


def _solar_height(moment, latitude, longitude):
    utc = moment.astimezone(timezone.utc)
    # NOAA's Julian-century equations avoid the several-minute seasonal error
    # of the shorter fractional-year approximation.
    century = (utc.timestamp() / 86400 + 2440587.5 - 2451545) / 36525
    longitude_mean = math.radians((280.46646 + century * (36000.76983 + 0.0003032 * century)) % 360)
    anomaly = math.radians(357.52911 + century * (35999.05029 - 0.0001537 * century))
    eccentricity = 0.016708634 - century * (0.000042037 + 0.0000001267 * century)
    center = (math.sin(anomaly) * (1.914602 - century * (0.004817 + 0.000014 * century))
              + math.sin(2 * anomaly) * (0.019993 - 0.000101 * century)
              + math.sin(3 * anomaly) * 0.000289)
    omega = math.radians(125.04 - 1934.136 * century)
    apparent = longitude_mean + math.radians(center - 0.00569 - 0.00478 * math.sin(omega))
    seconds = 21.448 - century * (46.815 + century * (0.00059 - century * 0.001813))
    obliquity = math.radians(23 + (26 + seconds / 60) / 60 + 0.00256 * math.cos(omega))
    declination = math.asin(math.sin(obliquity) * math.sin(apparent))
    y = math.tan(obliquity / 2) ** 2
    equation = 4 * math.degrees(y * math.sin(2 * longitude_mean) - 2 * eccentricity * math.sin(anomaly)
        + 4 * eccentricity * y * math.sin(anomaly) * math.cos(2 * longitude_mean)
        - 0.5 * y * y * math.sin(4 * longitude_mean)
        - 1.25 * eccentricity * eccentricity * math.sin(2 * anomaly))
    hour = utc.hour + utc.minute / 60 + utc.second / 3600 + utc.microsecond / 3.6e9
    angle = math.radians(((hour * 60 + equation + 4 * longitude) % 1440) / 4 - 180)
    lat = math.radians(latitude)
    cosine = math.sin(lat) * math.sin(declination) + math.cos(lat) * math.cos(declination) * math.cos(angle)
    return cosine - math.cos(math.radians(90.833))


def solar_times(local_date, latitude=MEDFORD_LATITUDE, longitude=MEDFORD_LONGITUDE):
    """Return epoch seconds for events on the given Pacific date, including DST."""
    start = datetime.combine(local_date, time(), MEDFORD_TIMEZONE).astimezone(timezone.utc)
    end = datetime.combine(local_date + timedelta(days=1), time(), MEDFORD_TIMEZONE).astimezone(timezone.utc)
    events = {"sunrise": None, "sunset": None}
    left = start
    previous = _solar_height(left, latitude, longitude)
    while left < end:
        right = min(left + timedelta(minutes=10), end)
        value = _solar_height(right, latitude, longitude)
        if (previous < 0) != (value < 0):
            low, high = left, right
            for _ in range(20):
                middle = low + (high - low) / 2
                if (_solar_height(middle, latitude, longitude) < 0) == (previous < 0):
                    low = middle
                else:
                    high = middle
            events["sunrise" if previous < 0 else "sunset"] = int((low + (high - low) / 2).timestamp())
        left, previous = right, value
    return events
