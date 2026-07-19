"""Meteostat (через RapidAPI) — данные метеостанций. Требует RapidAPI-ключ пользователя."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone

from ..models import WeatherSample
from .base import WeatherProvider, WeatherProviderError

_URL = "https://meteostat.p.rapidapi.com/point/hourly"
_HOST = "meteostat.p.rapidapi.com"


class MeteostatProvider(WeatherProvider):
    """Ближайшая станция Meteostat к переданным координатам, последний доступный час."""

    name = "Meteostat"

    @property
    def requires_api_key(self) -> bool:
        return True

    async def fetch_current(self, latitude: float, longitude: float) -> WeatherSample:
        today = datetime.now(dt_timezone.utc).date()
        yesterday = today - timedelta(days=1)
        response = await self._http.get(
            _URL,
            params={
                "lat": latitude,
                "lon": longitude,
                "start": yesterday.isoformat(),
                "end": today.isoformat(),
            },
            headers={"X-RapidAPI-Key": self._api_key or "", "X-RapidAPI-Host": _HOST},
        )
        self._raise_for_status(response)
        rows = response.json().get("data", [])
        if not rows:
            raise WeatherProviderError(f"{self.name}: нет наблюдений станции рядом с точкой")
        latest = rows[-1]

        return WeatherSample(
            temperature_c=latest.get("temp"),
            humidity_pct=latest.get("rhum"),
            wind_speed_ms=(latest.get("wspd") or 0) / 3.6 if latest.get("wspd") is not None else None,
            wind_direction_deg=latest.get("wdir"),
            precipitation_mm=latest.get("prcp"),
            pressure_hpa=latest.get("pres"),
            dew_point_c=latest.get("dwpt"),
        )
