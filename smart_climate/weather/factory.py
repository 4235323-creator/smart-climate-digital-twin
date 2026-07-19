"""Composition root Weather Data Fusion Engine — сборка каскада погодных провайдеров."""
from __future__ import annotations

import httpx

from ..domain.models import BuildingProfile
from .fusion import DataFusionEngine
from .providers import (
    MeteostatProvider,
    MetNorwayProvider,
    OpenMeteoEcmwfProvider,
    OpenMeteoGfsProvider,
    OpenMeteoProvider,
    OpenWeatherProvider,
    TomorrowIoProvider,
    WeatherApiProvider,
    WttrInProvider,
)


def build_data_fusion_engine(
    http_client: httpx.AsyncClient,
    building: BuildingProfile,
    *,
    openweather_api_key: str | None = None,
    meteostat_api_key: str | None = None,
    weatherapi_api_key: str | None = None,
    tomorrow_io_api_key: str | None = None,
    iqair_api_key: str | None = None,
) -> DataFusionEngine:
    """
    Каскад (по приоритету):
        ECMWF IFS → NOAA GFS (Open-Meteo, без ключа)
        → OpenWeather → Meteostat (нужен ключ)
        → Open-Meteo сводная модель (без ключа)
        → WeatherAPI.com → Tomorrow.io (нужен ключ)
        → MET Norway → wttr.in (без ключа, финальный резерв)
    """
    weather_providers = [
        OpenMeteoEcmwfProvider(http_client),
        OpenMeteoGfsProvider(http_client),
        OpenWeatherProvider(http_client, api_key=openweather_api_key),
        MeteostatProvider(http_client, api_key=meteostat_api_key),
        OpenMeteoProvider(http_client),
        WeatherApiProvider(http_client, api_key=weatherapi_api_key),
        TomorrowIoProvider(http_client, api_key=tomorrow_io_api_key),
        MetNorwayProvider(http_client),
        WttrInProvider(http_client),
    ]
    return DataFusionEngine(
        http_client=http_client,
        weather_providers=weather_providers,
        building=building,
        iqair_api_key=iqair_api_key,
    )


__all__ = ["build_data_fusion_engine"]
