"""
Абстракция Weather Provider.

СТРОГОЕ ПРАВИЛО: любой провайдер получает latitude/longitude ПАРАМЕТРАМИ вызова
и не хранит и не подразумевает никаких заранее заданных координат объектов.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import httpx

from ..models import WeatherSample


class WeatherProviderError(Exception):
    """Единая ошибка уровня погодного провайдера."""


class WeatherProvider(ABC):
    name: str = "BaseWeatherProvider"

    def __init__(self, http_client: httpx.AsyncClient, api_key: str | None = None) -> None:
        self._http = http_client
        self._api_key = api_key

    @property
    def requires_api_key(self) -> bool:
        return False

    def is_available(self) -> bool:
        return (not self.requires_api_key) or bool(self._api_key)

    @abstractmethod
    async def fetch_current(self, latitude: float, longitude: float) -> WeatherSample:
        """Возвращает текущие погодные данные исключительно для переданных координат."""
        raise NotImplementedError

    def _raise_for_status(self, response: httpx.Response) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise WeatherProviderError(f"{self.name} вернул HTTP {response.status_code}") from exc
