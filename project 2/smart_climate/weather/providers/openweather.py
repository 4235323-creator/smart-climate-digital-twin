"""OpenWeather — текущая погода. Требует бесплатный API-ключ пользователя."""
from __future__ import annotations

from datetime import datetime, timezone as dt_timezone

from ..models import WeatherSample
from .base import WeatherProvider

_URL = "https://api.openweathermap.org/data/2.5/weather"


class OpenWeatherProvider(WeatherProvider):
    name = "OpenWeather"

    @property
    def requires_api_key(self) -> bool:
        return True

    async def fetch_current(self, latitude: float, longitude: float) -> WeatherSample:
        response = await self._http.get(
            _URL,
            params={"lat": latitude, "lon": longitude, "appid": self._api_key, "units": "metric"},
        )
        self._raise_for_status(response)
        data = response.json()
        main = data.get("main", {})
        wind = data.get("wind", {})
        clouds = data.get("clouds", {})
        sys_ = data.get("sys", {})

        return WeatherSample(
            temperature_c=main.get("temp"),
            humidity_pct=main.get("humidity"),
            wind_speed_ms=wind.get("speed"),
            wind_direction_deg=wind.get("deg"),
            precipitation_mm=(data.get("rain", {}) or {}).get("1h"),
            pressure_hpa=main.get("pressure"),
            cloud_cover_pct=clouds.get("all"),
            visibility_m=data.get("visibility"),
            sunrise=self._to_iso(sys_.get("sunrise")),
            sunset=self._to_iso(sys_.get("sunset")),
        )

    @staticmethod
    def _to_iso(unix_ts: int | None) -> str | None:
        if unix_ts is None:
            return None
        return datetime.fromtimestamp(unix_ts, tz=dt_timezone.utc).isoformat()
