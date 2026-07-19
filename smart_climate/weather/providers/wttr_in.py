"""wttr.in — консольный погодный агрегатор, без ключа. Последний резерв каскада."""
from __future__ import annotations

from ..models import WeatherSample
from .base import WeatherProvider


class WttrInProvider(WeatherProvider):
    name = "wttr.in"

    async def fetch_current(self, latitude: float, longitude: float) -> WeatherSample:
        response = await self._http.get(
            f"https://wttr.in/{latitude},{longitude}", params={"format": "j1"}
        )
        self._raise_for_status(response)
        current = response.json()["current_condition"][0]

        return WeatherSample(
            temperature_c=float(current["temp_C"]),
            humidity_pct=float(current["humidity"]),
            wind_speed_ms=float(current["windspeedKmph"]) / 3.6,
            wind_direction_deg=float(current.get("winddirDegree", 0)) or None,
            cloud_cover_pct=float(current.get("cloudcover", 0)),
            pressure_hpa=float(current.get("pressure", 0)) or None,
            visibility_m=float(current.get("visibility", 0)) * 1000.0 if current.get("visibility") else None,
        )
