"""MET Norway (Yr.no) — официальный метеоинститут Норвегии, глобальное покрытие, без ключа."""
from __future__ import annotations

from ..models import WeatherSample
from .base import WeatherProvider

_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"


class MetNorwayProvider(WeatherProvider):
    name = "MET Norway (Yr.no)"

    async def fetch_current(self, latitude: float, longitude: float) -> WeatherSample:
        response = await self._http.get(
            _URL,
            params={"lat": latitude, "lon": longitude},
            headers={"User-Agent": "SmartClimateDigitalTwin/2.0 (contact: ops@example.com)"},
        )
        self._raise_for_status(response)
        details = response.json()["properties"]["timeseries"][0]["data"]["instant"]["details"]

        return WeatherSample(
            temperature_c=details.get("air_temperature"),
            humidity_pct=details.get("relative_humidity"),
            wind_speed_ms=details.get("wind_speed"),
            wind_direction_deg=details.get("wind_from_direction"),
            cloud_cover_pct=details.get("cloud_area_fraction"),
            pressure_hpa=details.get("air_pressure_at_sea_level"),
            dew_point_c=details.get("dew_point_temperature"),
            uv_index=details.get("ultraviolet_index_clear_sky"),
        )
