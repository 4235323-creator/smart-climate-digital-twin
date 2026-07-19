"""
Абстракция Geocoding Provider.

LocationResolver зависит только от этого интерфейса (Dependency Inversion),
а не от конкретных сервисов Nominatim/Photon/Google/Mapbox/HERE.
Это позволяет добавлять новые провайдеры или менять порядок каскада без
изменения кода резолвера (Open/Closed Principle).
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import httpx

from ...domain.models import LocationResult


class GeocodingProviderError(Exception):
    """Единая ошибка уровня провайдера геокодинга (сеть, парсинг, лимиты и т.д.)."""


class GeocodingProvider(ABC):
    """Базовый контракт для любого геокодинг-сервиса в каскаде."""

    #: Человекочитаемое имя источника — используется в логах и на дашборде.
    name: str = "BaseGeocodingProvider"

    def __init__(self, http_client: httpx.AsyncClient, api_key: str | None = None) -> None:
        self._http = http_client
        self._api_key = api_key

    @property
    def requires_api_key(self) -> bool:
        """Переопределяется в провайдерах, которым нужен платный/пороговый ключ."""
        return False

    def is_available(self) -> bool:
        """Провайдер пропускается в каскаде, если ему нужен ключ, а его нет."""
        return (not self.requires_api_key) or bool(self._api_key)

    @abstractmethod
    async def geocode(self, query: str, limit: int = 5) -> list[LocationResult]:
        """
        Прямое геокодирование произвольного текстового запроса:
        страна / область / город / посёлок / село / улица / дом /
        ТРЦ / бизнес-центр / предприятие — без ограничений по типу объекта.
        """
        raise NotImplementedError

    @abstractmethod
    async def reverse_geocode(self, latitude: float, longitude: float) -> LocationResult:
        """Обратное геокодирование: координаты → адрес/объект."""
        raise NotImplementedError

    def _raise_for_status(self, response: httpx.Response) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise GeocodingProviderError(
                f"{self.name} вернул HTTP {response.status_code}"
            ) from exc
