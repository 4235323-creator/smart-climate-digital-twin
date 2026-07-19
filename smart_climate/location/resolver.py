"""
Location Intelligence Engine — ядро универсального определения местоположения.

    Пользователь → название объекта / GPS
        → LocationResolver
            → каскад Geocoding Providers (Nominatim → Photon → Google → Mapbox → HERE)
        → Latitude/Longitude
        → Timezone (offline, timezonefinder)
        → Country / Region / City
    → готово для Weather Providers и MPC Controller

В коде нет ни одной заранее заданной координаты или объекта — резолвер
работает для абсолютно любой точки мира, которую способны разрешить
провайдеры геокодинга.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from timezonefinder import TimezoneFinder

from ..domain.models import LocationResult, LocationType
from ..infrastructure.http_client import build_http_client
from .cache import SmartLocationCache
from .providers.base import GeocodingProvider

logger = logging.getLogger(__name__)

_COORDINATE_PATTERN = re.compile(
    r"^\s*(-?\d{1,3}(?:\.\d+)?)\s*[,;\s]\s*(-?\d{1,3}(?:\.\d+)?)\s*$"
)


class LocationResolutionError(Exception):
    """Ни один провайдер каскада не смог разрешить запрос."""


class LocationResolver:
    """
    Универсальный резолвер местоположения.

    Умеет:
        * искать населённые пункты, адреса, ТРЦ, бизнес-центры, предприятия;
        * распознавать "сырые" GPS-координаты, введённые текстом;
        * определять местоположение устройства по (lat, lon) геолокации браузера;
        * выполнять обратное геокодирование (координаты → адрес);
        * автоматически переключаться на следующий Geocoding Provider при сбое;
        * не повторять геокодирование для уже запрошенных объектов (Smart Cache).
    """

    def __init__(
        self,
        providers: list[GeocodingProvider],
        cache: SmartLocationCache,
        timezone_finder: Optional[TimezoneFinder] = None,
    ) -> None:
        if not providers:
            raise ValueError("LocationResolver требует хотя бы один GeocodingProvider")
        self._providers = providers
        self._cache = cache
        self._tz_finder = timezone_finder or TimezoneFinder()

    # ------------------------------------------------------------------ #
    # Публичный API
    # ------------------------------------------------------------------ #

    async def search(self, query: str, limit: int = 5) -> list[LocationResult]:
        """
        Универсальный поиск по свободному тексту ИЛИ по "сырым" координатам.
        Работает для страны, области, города, посёлка, села, улицы, дома,
        ТРЦ, бизнес-центра, предприятия — без каких-либо ограничений.
        """
        query = query.strip()
        if not query:
            return []

        raw_coords = self._try_parse_coordinates(query)
        if raw_coords is not None:
            latitude, longitude = raw_coords
            return [await self.resolve_by_gps(latitude, longitude)]

        cache_key = f"search::{query}"
        cached = await self._cache.get(cache_key)
        if cached is not None:
            logger.info("Smart Cache: '%s' найден в кэше, повторный геокодинг пропущен", query)
            return cached[:limit]

        results, used_provider = await self._geocode_cascade(query, limit)
        if not results:
            raise LocationResolutionError(
                f"Не удалось разрешить местоположение для запроса: '{query}'. "
                "Все провайдеры каскада недоступны или не нашли объект."
            )

        enriched = [await self._enrich(result) for result in results]
        await self._cache.set(cache_key, enriched)
        logger.info("'%s' разрешён через %s", query, used_provider)
        return enriched

    async def resolve_by_gps(
        self,
        latitude: float,
        longitude: float,
        elevation_m: Optional[float] = None,
    ) -> LocationResult:
        """
        Определение местоположения по GPS-координатам устройства
        (используется, когда пользователь разрешил геолокацию браузера,
        либо когда введена пара координат вручную).
        """
        cache_key = f"gps::{round(latitude, 5)}::{round(longitude, 5)}"
        cached = await self._cache.get(cache_key)
        if cached is not None:
            result = cached[0]
            if elevation_m is not None and result.elevation_m is None:
                result = result.with_updates(elevation_m=elevation_m)
            return result

        result = await self._reverse_geocode_cascade(latitude, longitude)
        result = await self._enrich(result, elevation_override=elevation_m)
        await self._cache.set(cache_key, [result])
        return result

    async def reverse_geocode(self, latitude: float, longitude: float) -> LocationResult:
        """Явное обратное геокодирование (алиас resolve_by_gps без учёта высоты устройства)."""
        return await self.resolve_by_gps(latitude, longitude)

    # ------------------------------------------------------------------ #
    # Внутренняя механика каскада
    # ------------------------------------------------------------------ #

    async def _geocode_cascade(self, query: str, limit: int) -> tuple[list[LocationResult], str]:
        for provider in self._providers:
            if not provider.is_available():
                logger.debug("Провайдер %s пропущен: нет API-ключа", provider.name)
                continue
            try:
                results = await provider.geocode(query, limit=limit)
                if results:
                    return results, provider.name
            except Exception as exc:  # noqa: BLE001 — сознательно широкий перехват для каскада
                logger.warning("Geocoding provider %s недоступен: %s", provider.name, exc)
                continue
        return [], "none"

    async def _reverse_geocode_cascade(self, latitude: float, longitude: float) -> LocationResult:
        for provider in self._providers:
            if not provider.is_available():
                continue
            try:
                return await provider.reverse_geocode(latitude, longitude)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Reverse geocoding через %s недоступен: %s", provider.name, exc)
                continue

        logger.error("Все провайдеры реверс-геокодинга недоступны, используем только координаты")
        return LocationResult(
            query=f"{latitude},{longitude}",
            display_name=f"{latitude:.5f}, {longitude:.5f}",
            name=f"{latitude:.5f}, {longitude:.5f}",
            latitude=latitude,
            longitude=longitude,
            location_type=LocationType.COORDINATES,
            provider="fallback (координаты без адреса)",
        )

    async def _enrich(
        self, result: LocationResult, elevation_override: Optional[float] = None
    ) -> LocationResult:
        """Добавляет timezone (offline) и высоту над уровнем моря (Open-Meteo Elevation API)."""
        timezone_name = result.timezone or self._tz_finder.timezone_at(
            lat=result.latitude, lng=result.longitude
        )
        elevation = elevation_override if elevation_override is not None else result.elevation_m
        if elevation is None:
            elevation = await self._fetch_elevation(result.latitude, result.longitude)
        return result.with_updates(timezone=timezone_name, elevation_m=elevation)

    @staticmethod
    async def _fetch_elevation(latitude: float, longitude: float) -> Optional[float]:
        """Высота над уровнем моря — бесплатный Open-Meteo Elevation API, без ключа."""
        try:
            async with build_http_client() as client:
                response = await client.get(
                    "https://api.open-meteo.com/v1/elevation",
                    params={"latitude": latitude, "longitude": longitude},
                )
                response.raise_for_status()
                elevations = response.json().get("elevation") or []
                return float(elevations[0]) if elevations else None
        except Exception as exc:  # noqa: BLE001
            logger.debug("Не удалось получить высоту рельефа: %s", exc)
            return None

    @staticmethod
    def _try_parse_coordinates(query: str) -> Optional[tuple[float, float]]:
        match = _COORDINATE_PATTERN.match(query)
        if not match:
            return None
        latitude, longitude = float(match.group(1)), float(match.group(2))
        if -90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0:
            return latitude, longitude
        return None
