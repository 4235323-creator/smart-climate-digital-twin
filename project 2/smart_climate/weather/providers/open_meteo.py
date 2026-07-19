"""Open-Meteo — основной бесплатный источник погоды без API-ключа. Поддерживает выбор модели (ECMWF/GFS)."""
from __future__ import annotations

from datetime import datetime, timezone as dt_timezone
from typing import Optional

from ..models import WeatherSample
from .base import WeatherProvider

_URL = "https://api.open-meteo.com/v1/forecast"

_CURRENT_FIELDS = (
    "temperature_2m,relative_humidity_2m,dew_point_2m,wind_speed_10m,wind_direction_10m,"
    "cloud_cover,pressure_msl,precipitation,direct_radiation,diffuse_radiation,is_day"
)
_HOURLY_FIELDS = "precipitation_probability,uv_index,visibility,soil_temperature_0cm"
_DAILY_FIELDS = "sunrise,sunset"


class _BaseOpenMeteoProvider(WeatherProvider):
    """Общая реализация: конкретную модель прогноза задаёт подкласс через `_model`."""

    _model: Optional[str] = None

    async def fetch_current(self, latitude: float, longitude: float) -> WeatherSample:
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": _CURRENT_FIELDS,
            "hourly": _HOURLY_FIELDS,
            "daily": _DAILY_FIELDS,
            "timezone": "auto",
        }
        if self._model:
            params["models"] = self._model

        response = await self._http.get(_URL, params=params)
        self._raise_for_status(response)
        payload = response.json()

        current = payload.get("current", {})
        if current.get("temperature_2m") is None:
            from .base import WeatherProviderError

            raise WeatherProviderError(f"{self.name}: нет данных для точки ({latitude}, {longitude})")

        hourly_value = self._current_hour_value(payload)

        return WeatherSample(
            temperature_c=current.get("temperature_2m"),
            humidity_pct=current.get("relative_humidity_2m"),
            wind_speed_ms=current.get("wind_speed_10m"),
            wind_direction_deg=current.get("wind_direction_10m"),
            precipitation_mm=current.get("precipitation"),
            precipitation_probability_pct=hourly_value("precipitation_probability"),
            pressure_hpa=current.get("pressure_msl"),
            cloud_cover_pct=current.get("cloud_cover"),
            direct_radiation_wm2=current.get("direct_radiation"),
            diffuse_radiation_wm2=current.get("diffuse_radiation"),
            uv_index=hourly_value("uv_index"),
            visibility_m=hourly_value("visibility"),
            soil_temperature_c=hourly_value("soil_temperature_0cm"),
            dew_point_c=current.get("dew_point_2m"),
            sunrise=self._today_daily_value(payload, "sunrise"),
            sunset=self._today_daily_value(payload, "sunset"),
            is_day=bool(current.get("is_day")) if current.get("is_day") is not None else None,
        )

    @staticmethod
    def _current_hour_value(payload: dict):
        hourly = payload.get("hourly", {})
        times = hourly.get("time", [])
        if not times:
            return lambda _field: None

        now = datetime.now(dt_timezone.utc).replace(minute=0, second=0, microsecond=0)
        try:
            target_index = min(
                range(len(times)),
                key=lambda i: abs(
                    datetime.fromisoformat(times[i]).replace(tzinfo=dt_timezone.utc) - now
                ),
            )
        except (ValueError, IndexError):
            target_index = 0

        def _get(field_name: str):
            series = hourly.get(field_name)
            if not series or target_index >= len(series):
                return None
            return series[target_index]

        return _get

    @staticmethod
    def _today_daily_value(payload: dict, field_name: str) -> Optional[str]:
        daily = payload.get("daily", {})
        series = daily.get(field_name)
        return series[0] if series else None


class OpenMeteoProvider(_BaseOpenMeteoProvider):
    """Сводная модель Open-Meteo по умолчанию (best-match)."""

    name = "Open-Meteo (сводная модель)"
    _model = None


class OpenMeteoEcmwfProvider(_BaseOpenMeteoProvider):
    """Модель ECMWF IFS через Open-Meteo — наивысший приоритет по точности в Европе."""

    name = "ECMWF IFS (via Open-Meteo)"
    _model = "ecmwf_ifs025"


class OpenMeteoGfsProvider(_BaseOpenMeteoProvider):
    """Модель NOAA GFS через Open-Meteo — глобальный резерв."""

    name = "NOAA GFS (via Open-Meteo)"
    _model = "gfs_seamless"
