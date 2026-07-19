"""
Weather Data Fusion Engine.

Работает ИСКЛЮЧИТЕЛЬНО через Latitude/Longitude, полученные от
Location Intelligence Engine. Никаких заранее заданных координат объектов
в этом модуле нет и быть не может — LocationResult приходит извне.
"""
from __future__ import annotations

import logging
from datetime import datetime

import httpx
import numpy as np

from ..domain.models import BuildingProfile, LocationResult
from .models import FusedDataState, WeatherSample
from .providers.base import WeatherProvider

logger = logging.getLogger(__name__)


class DataFusionEngine:
    """
    Центральный процессор слияния данных.
    Объединяет каскад погодных провайдеров, календарную сетку, профиль трафика
    здания и датчики качества воздуха/осадков — всё привязано только к координатам.
    """

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        weather_providers: list[WeatherProvider],
        building: BuildingProfile,
        iqair_api_key: str | None = None,
    ) -> None:
        self._http = http_client
        self._weather_providers = weather_providers
        self._building = building
        self._iqair_api_key = iqair_api_key

    # ------------------------------------------------------------------ #
    # Погодный каскад
    # ------------------------------------------------------------------ #

    async def fetch_weather_cascade(
        self, latitude: float, longitude: float
    ) -> tuple[WeatherSample, dict[str, str], str]:
        """Каскадный опрос провайдеров: первый успешный — приоритетный источник, остальные добирают недостающие поля."""
        status: dict[str, str] = {}
        merged = WeatherSample()
        primary_source: str | None = None

        for provider in self._weather_providers:
            if not provider.is_available():
                status[provider.name] = "🔒 Пропущен (нет API-ключа)"
                continue
            try:
                sample = await provider.fetch_current(latitude, longitude)
                status[provider.name] = "✅ Ответил"
                if primary_source is None:
                    primary_source = provider.name
                merged = merged.merge_missing_from(sample)
            except Exception as exc:  # noqa: BLE001 — каскад должен продолжать при любой ошибке источника
                status[provider.name] = f"❌ Недоступен ({type(exc).__name__})"
                logger.warning("Weather provider %s недоступен: %s", provider.name, exc)

        if primary_source is None:
            status["Аварийный фолбэк"] = "⚠️ Использованы консервативные значения по умолчанию"
            merged = WeatherSample(
                temperature_c=25.0, humidity_pct=50.0, wind_speed_ms=3.0,
                cloud_cover_pct=40.0, is_day=True,
            )
            primary_source = "Аварийный фолбэк"

        if merged.direct_radiation_wm2 is None or merged.diffuse_radiation_wm2 is None:
            direct_est, diffuse_est = self._estimate_solar_radiation(
                datetime.now(), merged.cloud_cover_pct or 40.0
            )
            merged.direct_radiation_wm2 = merged.direct_radiation_wm2 or direct_est
            merged.diffuse_radiation_wm2 = merged.diffuse_radiation_wm2 or diffuse_est
            status["Радиация (расчётная модель)"] = "🧮 Оценена по времени суток и облачности"

        if merged.is_day is None:
            hour = datetime.now().hour
            merged.is_day = 6 <= hour <= 20

        return merged, status, primary_source

    @staticmethod
    def _estimate_solar_radiation(now: datetime, cloud_cover_pct: float) -> tuple[float, float]:
        """Оценка солнечной радиации по времени суток и облачности, если ни один провайдер её не дал."""
        hour_decimal = now.hour + now.minute / 60.0
        daylight_factor = (
            max(0.0, np.sin((hour_decimal - 6.0) / 12.0 * np.pi)) if 6.0 <= hour_decimal <= 20.0 else 0.0
        )
        clear_sky_max = 850.0
        direct = clear_sky_max * daylight_factor * (1.0 - cloud_cover_pct / 100.0) * 0.8
        diffuse = clear_sky_max * daylight_factor * (cloud_cover_pct / 100.0) * 0.3
        return round(direct, 1), round(diffuse, 1)

    # ------------------------------------------------------------------ #
    # Контекстные данные (календарь / трафик / тариф / качество воздуха)
    # ------------------------------------------------------------------ #

    def evaluate_calendar_and_occupancy(self, now: datetime) -> tuple[str, bool, int]:
        """Паттерн Popular Times, масштабированный под объём КОНКРЕТНОГО здания (BuildingProfile), а не под ТРЦ по имени."""
        day_of_week = now.weekday()
        hour = now.hour

        is_holiday = day_of_week in (5, 6)
        calendar_event = "Регулярный день"
        if is_holiday:
            calendar_event = "Выходной день (Повышенный трафик)"
        if now.month == 12 and now.day == 25:
            is_holiday = True
            calendar_event = "Рождество (Пик сезона)"

        if 10 <= hour <= 22:
            base_factor = 0.3 if hour < 13 else (0.9 if 17 <= hour <= 20 else 0.6)
            if is_holiday:
                base_factor *= 1.4
            estimated_people = int((self._building.volume_m3 / 30.0) * base_factor)
        else:
            estimated_people = 0
            calendar_event = "Объект закрыт"

        return calendar_event, is_holiday, estimated_people

    @staticmethod
    def fetch_electricity_price(now: datetime) -> float:
        """Упрощённая модель спотового тарифа (день/ночь/пик) — независима от местоположения."""
        hour = now.hour
        if 17 <= hour <= 22:
            return 0.18
        if 8 <= hour <= 16:
            return 0.12
        return 0.05

    async def fetch_iqair_aqi(self, latitude: float, longitude: float) -> tuple[int | None, str]:
        if not self._iqair_api_key:
            return None, "🔒 Пропущен (нет API-ключа IQAir)"
        try:
            response = await self._http.get(
                "http://api.airvisual.com/v2/nearest_city",
                params={"lat": latitude, "lon": longitude, "key": self._iqair_api_key},
            )
            response.raise_for_status()
            pollution = response.json()["data"]["current"]["pollution"]
            return pollution.get("aqius"), "✅ Ответил"
        except Exception as exc:  # noqa: BLE001
            return None, f"❌ Недоступен ({type(exc).__name__})"

    async def fetch_precipitation_radar_status(self) -> str:
        try:
            response = await self._http.get("https://api.rainviewer.com/public/weather-maps.json")
            response.raise_for_status()
            past_frames = response.json().get("radar", {}).get("past", [])
            if not past_frames:
                return "⚠️ Нет доступных кадров"
            last_frame = past_frames[-1]
            last_time = datetime.fromtimestamp(last_frame["time"]).isoformat()
            return f"✅ Доступно кадров: {len(past_frames)}, последний: {last_time}"
        except Exception as exc:  # noqa: BLE001
            return f"❌ Недоступен ({type(exc).__name__})"

    # ------------------------------------------------------------------ #
    # Точка входа
    # ------------------------------------------------------------------ #

    async def fuse_all_streams(self, location: LocationResult) -> FusedDataState:
        now = datetime.now()
        weather, weather_status, primary_source = await self.fetch_weather_cascade(
            location.latitude, location.longitude
        )
        event, is_holiday, occupancy = self.evaluate_calendar_and_occupancy(now)
        price = self.fetch_electricity_price(now)
        aqi_value, aqi_status = await self.fetch_iqair_aqi(location.latitude, location.longitude)
        radar_status = await self.fetch_precipitation_radar_status()

        return FusedDataState(
            timestamp=now,
            location=location,
            out_temp=weather.temperature_c if weather.temperature_c is not None else 25.0,
            out_humidity=weather.humidity_pct if weather.humidity_pct is not None else 50.0,
            wind_speed=weather.wind_speed_ms if weather.wind_speed_ms is not None else 3.0,
            wind_direction=weather.wind_direction_deg,
            precipitation_mm=weather.precipitation_mm or 0.0,
            precipitation_probability_pct=weather.precipitation_probability_pct or 0.0,
            pressure_hpa=weather.pressure_hpa or 1013.0,
            cloud_cover=weather.cloud_cover_pct if weather.cloud_cover_pct is not None else 20.0,
            direct_radiation=weather.direct_radiation_wm2 or 0.0,
            diffuse_radiation=weather.diffuse_radiation_wm2 or 0.0,
            uv_index=weather.uv_index or 0.0,
            visibility_m=weather.visibility_m or 10000.0,
            soil_temperature=weather.soil_temperature_c if weather.soil_temperature_c is not None else (weather.temperature_c or 20.0),
            dew_point=weather.dew_point_c if weather.dew_point_c is not None else (weather.temperature_c or 15.0) - 5.0,
            sunrise=weather.sunrise,
            sunset=weather.sunset,
            is_daylight=bool(weather.is_day),
            estimated_occupancy=occupancy,
            electricity_price_usd_kwh=price,
            calendar_event=event,
            is_holiday=is_holiday,
            weather_sources_status=weather_status,
            weather_primary_source=primary_source,
            air_quality_aqi=aqi_value,
            air_quality_source_status=aqi_status,
            precipitation_radar_status=radar_status,
        )

    @staticmethod
    def apply_scenario(state: FusedDataState, scenario: str) -> FusedDataState:
        """Модификация слитого состояния под выбранный стресс-сценарий (для демонстрации Digital Twin)."""
        if scenario == "Тепловая волна (+40°C)":
            state.out_temp = 40.0
            state.direct_radiation = max(state.direct_radiation, 850.0)
            state.cloud_cover = 5.0
        elif scenario == "Чёрная пятница (x2 поток людей)":
            state.estimated_occupancy = int(state.estimated_occupancy * 2.2)
            state.calendar_event = "Пиковый трафик (Экстремальная нагрузка)"
        elif scenario == "Скачок цены на электроэнергию (x3)":
            state.electricity_price_usd_kwh = round(state.electricity_price_usd_kwh * 3.0, 3)
        elif scenario == "Авария датчика температуры":
            state.out_temp = state.out_temp + float(np.random.uniform(-6.0, 6.0))
        return state
