#!/usr/bin/env python3
import json
import time
import urllib.parse
import urllib.request

from smarthome_config import (
    WEATHER_API_KEY,
    WEATHER_LOCATION,
    WEATHER_LOOKAHEAD_HOURS,
    RAIN_CHANCE_THRESHOLD,
    WEATHER_REFRESH_INTERVAL,
    WEATHER_TIMEOUT_SECONDS,
)


class WeatherGuard:
    def __init__(self):
        self._last_fetch = 0
        self._cached = {
            "rain_expected_next_5h": False,
            "rain_block_watering": False,
            "weather_ok": False,
            "weather_reason": "not_checked",
        }

    def check(self):
        now = time.monotonic()
        if now - self._last_fetch < WEATHER_REFRESH_INTERVAL:
            return self._cached

        self._last_fetch = now
        try:
            self._cached = self._fetch()
        except Exception as exc:
            self._cached = {
                "rain_expected_next_5h": False,
                "rain_block_watering": False,
                "weather_ok": False,
                "weather_reason": f"weather_error:{exc}",
            }
        return self._cached

    def _fetch(self):
        if not WEATHER_API_KEY:
            return {
                "rain_expected_next_5h": False,
                "rain_block_watering": False,
                "weather_ok": False,
                "weather_reason": "weather_api_key_missing",
            }

        params = urllib.parse.urlencode({
            "key": WEATHER_API_KEY,
            "q": WEATHER_LOCATION,
            "days": 2,
            "aqi": "no",
            "alerts": "no",
        })
        url = f"https://api.weatherapi.com/v1/forecast.json?{params}"
        with urllib.request.urlopen(url, timeout=WEATHER_TIMEOUT_SECONDS) as response:
            data = json.loads(response.read().decode("utf-8"))

        now_epoch = int(time.time())
        end_epoch = now_epoch + WEATHER_LOOKAHEAD_HOURS * 3600
        risky_hours = []

        for day in data.get("forecast", {}).get("forecastday", []):
            for hour in day.get("hour", []):
                ts = int(hour.get("time_epoch", 0))
                if now_epoch <= ts <= end_epoch:
                    chance = int(hour.get("chance_of_rain", 0))
                    will_rain = int(hour.get("will_it_rain", 0))
                    precip = float(hour.get("precip_mm", 0.0))
                    if will_rain == 1 or chance >= RAIN_CHANCE_THRESHOLD or precip > 0:
                        risky_hours.append({
                            "time": hour.get("time"),
                            "chance_of_rain": chance,
                            "will_it_rain": will_rain,
                            "precip_mm": precip,
                        })

        rain_expected = len(risky_hours) > 0
        return {
            "rain_expected_next_5h": rain_expected,
            "rain_block_watering": rain_expected,
            "weather_ok": True,
            "weather_reason": "rain_expected" if rain_expected else "clear",
            "rain_risky_hours": risky_hours[:5],
            "weather_location": WEATHER_LOCATION,
        }
