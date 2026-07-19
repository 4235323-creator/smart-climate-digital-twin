"""
Доменные модели слоя Location Intelligence.

ВАЖНО: в этом модуле нет ни одной заранее заданной координаты или объекта.
LocationResult — это универсальное представление ЛЮБОЙ точки мира,
полученное динамически через Geocoding Providers.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LocationType(str, Enum):
    """Тип объекта, который умеет распознавать LocationResolver."""

    COUNTRY = "country"
    REGION = "region"
    CITY = "city"
    TOWN = "town"
    VILLAGE = "village"
    STREET = "street"
    ADDRESS = "address"
    MALL = "mall"
    BUSINESS_CENTER = "business_center"
    BUSINESS = "business"
    BUILDING = "building"
    COORDINATES = "coordinates"
    UNKNOWN = "unknown"


class LocationResult(BaseModel):
    """
    Универсальный результат разрешения местоположения.

    Заполняется исключительно во время выполнения одним из Geocoding Providers
    (Nominatim / Photon / Google / Mapbox / HERE) либо обратным геокодированием
    по GPS-координатам устройства пользователя.
    """

    model_config = ConfigDict(frozen=True)

    query: str = Field(..., description="Исходный пользовательский запрос")
    display_name: str = Field(..., description="Полное отображаемое имя объекта")
    name: str = Field(..., description="Короткое имя объекта")

    latitude: float
    longitude: float
    elevation_m: Optional[float] = None

    country: Optional[str] = None
    country_code: Optional[str] = None
    region: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    postcode: Optional[str] = None

    location_type: LocationType = LocationType.UNKNOWN
    timezone: Optional[str] = None

    provider: str = "unknown"
    raw: dict[str, Any] = Field(default_factory=dict, repr=False)

    @field_validator("latitude")
    @classmethod
    def _validate_lat(cls, value: float) -> float:
        if not -90.0 <= value <= 90.0:
            raise ValueError(f"Некорректная широта: {value}")
        return value

    @field_validator("longitude")
    @classmethod
    def _validate_lon(cls, value: float) -> float:
        if not -180.0 <= value <= 180.0:
            raise ValueError(f"Некорректная долгота: {value}")
        return value

    @property
    def coordinates(self) -> tuple[float, float]:
        return (self.latitude, self.longitude)

    def with_updates(self, **kwargs: Any) -> "LocationResult":
        """Иммутабельное обновление (модель заморожена)."""
        return self.model_copy(update=kwargs)


class BuildingProfile(BaseModel):
    """
    Параметры конкретного здания, независимые от местоположения.

    Раньше эти цифры были жёстко зашиты в словаре MALLS для трёх ТРЦ Киева.
    Теперь система работает с ЛЮБОЙ точкой мира, поэтому объём здания и базовую
    нагрузку задаёт пользователь (или BMS/CAD-интеграция) — это атрибут
    объекта автоматизации, а не атрибут местоположения.
    """

    model_config = ConfigDict(frozen=True)

    volume_m3: float = Field(gt=0, description="Отапливаемый/охлаждаемый объём здания, м³")
    base_load_kw: float = Field(ge=0, description="Базовая (не HVAC) электрическая нагрузка, кВт")
    label: str = ""
