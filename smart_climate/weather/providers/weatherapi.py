"""WeatherAPI.com — текущая погода + astro (sunrise/sunset). Требует API-ключ."""
from __future__ import annotations

from ..models import WeatherSample
from .base import WeatherProvider

_URL = "https://api.weatherapi.com/v1/forecast.json"


class WeatherApiProvider(WeatherProvider):
    name = "WeatherAPI.com"

    @property
    def requires_api_key(self) -> bool:
        return True

    async def fetch_current(self, latitude: float, longitude: float) -> WeatherSample:
        response = await self._http.get(
            _URL,
            params={"key": self._api_key, "q": f"{latitude},{longitude}", "days": 1, "aqi": "no"},
        )
        self._raise_for_status(response)
        payload = response.json()
        current = payload.get("current", {})
        forecast_days = payload.get("forecast", {}).get("forecastday", [])
        astro = forecast_days[0].get("astro", {}) if forecast_days else {}

        wind_kph = current.get("wind_kph")
        vis_km = current.get("vis_km")

        return WeatherSample(
            temperature_c=current.get("temp_c"),
            humidity_pct=current.get("humidity"),
            wind_speed_ms=(wind_kph / 3.6) if wind_kph is not None else None,
            wind_direction_deg=current.get("wind_degree"),
            precipitation_mm=current.get("precip_mm"),
            pressure_hpa=current.get("pressure_mb"),
            cloud_cover_pct=current.get("cloud"),
            uv_index=current.get("uv"),
            visibility_m=(vis_km * 1000.0) if vis_km is not None else None,
            sunrise=astro.get("sunrise"),
            sunset=astro.get("sunset"),
            is_day=bool(current.get("is_day")) if current.get("is_day") is not None else None,
        )
