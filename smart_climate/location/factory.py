"""
Composition root Location Intelligence Engine.

Здесь и только здесь происходит "сборка" каскада провайдеров.
Все остальные слои (resolver, weather, UI) зависят от абстракций,
а не от конкретных реализаций — классический Dependency Injection.
"""
from __future__ import annotations

from pathlib import Path

import httpx

from ..infrastructure.http_client import build_http_client
from .cache import SmartLocationCache
from .providers import (
    GoogleGeocodingProvider,
    HereMapsProvider,
    MapboxProvider,
    NominatimProvider,
    PhotonProvider,
)
from .resolver import LocationResolver


def build_location_resolver(
    http_client: httpx.AsyncClient,
    *,
    google_api_key: str | None = None,
    mapbox_api_key: str | None = None,
    here_api_key: str | None = None,
    cache_ttl_seconds: int = 24 * 3600,
    cache_persist_path: Path | None = None,
) -> LocationResolver:
    """
    Собирает LocationResolver с полным каскадом:
        Nominatim → Photon → Google → Mapbox → HERE Maps.

    Провайдеры без ключа (Nominatim, Photon) всегда активны.
    Провайдеры с ключом (Google, Mapbox, HERE) автоматически пропускаются
    в каскаде, если соответствующий ключ не передан пользователем.
    """
    providers = [
        NominatimProvider(http_client),
        PhotonProvider(http_client),
        GoogleGeocodingProvider(http_client, api_key=google_api_key),
        MapboxProvider(http_client, api_key=mapbox_api_key),
        HereMapsProvider(http_client, api_key=here_api_key),
    ]
    cache = SmartLocationCache(ttl_seconds=cache_ttl_seconds, persist_path=cache_persist_path)
    return LocationResolver(providers=providers, cache=cache)


__all__ = ["build_location_resolver", "build_http_client"]
