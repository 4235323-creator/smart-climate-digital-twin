"""Модели данных слоя Weather Data Fusion. Все погодные поля привязаны только к lat/lon."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ..domain.models import LocationResult


@dataclass(slots=True)
class WeatherSample:
    """Единый нормализованный ответ погодного провайдера (частично заполненный допустим)."""

    temperature_c: Optional[float] = None
    humidity_pct: Optional[float] = None
    wind_speed_ms: Optional[float] = None
    wind_direction_deg: Optional[float] = None
    precipitation_mm: Optional[float] = None
    precipitation_probability_pct: Optional[float] = None
    pressure_hpa: Optional[float] = None
    cloud_cover_pct: Optional[float] = None
    direct_radiation_wm2: Optional[float] = None
    diffuse_radiation_wm2: Optional[float] = None
    uv_index: Optional[float] = None
    visibility_m: Optional[float] = None
    soil_temperature_c: Optional[float] = None
    dew_point_c: Optional[float] = None
    sunrise: Optional[str] = None
    sunset: Optional[str] = None
    is_day: Optional[bool] = None

    def merge_missing_from(self, other: "WeatherSample") -> "WeatherSample":
        """Заполняет только те поля, которых ещё нет (используется в каскаде провайдеров)."""
        updated = {}
        for attr in self.__dataclass_fields__:
            current_value = getattr(self, attr)
            if current_value is None:
                updated[attr] = getattr(other, attr)
            else:
                updated[attr] = current_value
        return WeatherSample(**updated)


@dataclass(slots=True)
class FusedDataState:
    """Итоговое состояние после слияния погоды, календаря, тарифа и датчиков качества воздуха."""

    timestamp: datetime
    location: LocationResult

    out_temp: float
    out_humidity: float
    wind_speed: float
    wind_direction: Optional[float]
    precipitation_mm: float
    precipitation_probability_pct: float
    pressure_hpa: float
    cloud_cover: float
    direct_radiation: float
    diffuse_radiation: float
    uv_index: float
    visibility_m: float
    soil_temperature: float
    dew_point: float
    sunrise: Optional[str]
    sunset: Optional[str]
    is_daylight: bool

    estimated_occupancy: int
    electricity_price_usd_kwh: float
    calendar_event: str
    is_holiday: bool

    weather_sources_status: dict[str, str] = field(default_factory=dict)
    weather_primary_source: str = "none"
    air_quality_aqi: Optional[int] = None
    air_quality_source_status: str = ""
    precipitation_radar_status: str = ""

    @property
    def object_name(self) -> str:
        return self.location.name
