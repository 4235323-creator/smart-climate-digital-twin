"""Tomorrow.io — realtime погода с высокой плотностью параметров. Требует API-ключ."""
from __future__ import annotations

from ..models import WeatherSample
from .base import WeatherProvider

_URL = "https://api.tomorrow.io/v4/weather/realtime"


class TomorrowIoProvider(WeatherProvider):
    name = "Tomorrow.io"

    @property
    def requires_api_key(self) -> bool:
        return True

    async def fetch_current(self, latitude: float, longitude: float) -> WeatherSample:
        response = await self._http.get(
            _URL,
            params={
                "location": f"{latitude},{longitude}",
                "apikey": self._api_key,
                "units": "metric",
            },
        )
        self._raise_for_status(response)
        values = response.json().get("data", {}).get("values", {})

        return WeatherSample(
            temperature_c=values.get("temperature"),
            humidity_pct=values.get("humidity"),
            wind_speed_ms=values.get("windSpeed"),
            wind_direction_deg=values.get("windDirection"),
            precipitation_mm=values.get("precipitationIntensity"),
            precipitation_probability_pct=values.get("precipitationProbability"),
            pressure_hpa=values.get("pressureSeaLevel"),
            cloud_cover_pct=values.get("cloudCover"),
            uv_index=values.get("uvIndex"),
            visibility_m=(values["visibility"] * 1000.0) if values.get("visibility") is not None else None,
            dew_point_c=values.get("dewPoint"),
        )
