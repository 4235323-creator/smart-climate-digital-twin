"""
Smart Climate — Commercial Digital Twin Platform (v2)
Слой интерфейса пользователя (Streamlit).

Архитектура:
    User → Location Intelligence Engine → Geocoding Providers → Coordinates
         → Weather Data Fusion → Forecast → MPC Controller → HVAC → Dashboard

В этом модуле нет ни одной заранее заданной координаты — пользователь
вводит ЛЮБОЙ объект (страну, город, ТРЦ, адрес, координаты) или использует
геолокацию устройства, и вся система работает от результата резолвера.
"""
from __future__ import annotations

import copy
import html
import logging
import time

import pandas as pd
import streamlit as st

from smart_climate.control.mpc import MpcOptimizer
from smart_climate.domain.models import BuildingProfile, LocationResult
from smart_climate.equipment.factory import build_equipment_health_engine
from smart_climate.equipment.models import EquipmentFleetHealth
from smart_climate.infrastructure.async_utils import run_async
from smart_climate.infrastructure.http_client import build_http_client
from smart_climate.location.factory import build_location_resolver
from smart_climate.location.resolver import LocationResolutionError
from smart_climate.mall_analytics.factory import build_mall_analytics_engine
from smart_climate.mall_analytics.models import MallAnalyticsReport
from smart_climate.vision.factory import build_computer_vision_engine
from smart_climate.vision.models import OccupancySnapshot
from smart_climate.weather.factory import build_data_fusion_engine
from smart_climate.weather.fusion import DataFusionEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("smart_climate.app")

st.set_page_config(page_title="Smart Climate Digital Twin", layout="wide")


# ────────────────────────────────────────────────────────────────────────
# Асинхронные точки входа (каждая открывает свой короткоживущий HTTP-клиент)
# ────────────────────────────────────────────────────────────────────────

async def _search_location(query: str, geo_keys: dict) -> list[LocationResult]:
    async with build_http_client() as client:
        resolver = build_location_resolver(
            client,
            google_api_key=geo_keys.get("google"),
            mapbox_api_key=geo_keys.get("mapbox"),
            here_api_key=geo_keys.get("here"),
        )
        return await resolver.search(query, limit=6)


async def _resolve_by_gps(lat: float, lon: float, elevation: float | None, geo_keys: dict) -> LocationResult:
    async with build_http_client() as client:
        resolver = build_location_resolver(
            client,
            google_api_key=geo_keys.get("google"),
            mapbox_api_key=geo_keys.get("mapbox"),
            here_api_key=geo_keys.get("here"),
        )
        return await resolver.resolve_by_gps(lat, lon, elevation_m=elevation)


async def _fetch_fused_weather(location: LocationResult, building: BuildingProfile, weather_keys: dict):
    async with build_http_client() as client:
        engine = build_data_fusion_engine(
            client,
            building,
            openweather_api_key=weather_keys.get("openweather"),
            meteostat_api_key=weather_keys.get("meteostat"),
            weatherapi_api_key=weather_keys.get("weatherapi"),
            tomorrow_io_api_key=weather_keys.get("tomorrow_io"),
            iqair_api_key=weather_keys.get("iqair"),
        )
        return await engine.fuse_all_streams(location)


async def _analyze_cv_occupancy() -> OccupancySnapshot:
    engine = build_computer_vision_engine()
    return await engine.analyze_occupancy()


async def _evaluate_equipment_health() -> EquipmentFleetHealth:
    engine = build_equipment_health_engine()
    return await engine.evaluate_fleet()


async def _build_mall_analytics_report(
    occupancy: OccupancySnapshot,
    mpc_result,
) -> MallAnalyticsReport:
    engine = build_mall_analytics_engine()
    return await engine.build_daily_report(occupancy, mpc_result)


def _build_scenario_catalog() -> list[dict[str, str]]:
    return [
        {
            "Scenario": "Обычный день",
            "Trigger": "Базовый профиль трафика",
            "HVAC Impact": "стандартный контроль",
            "MPC Action": "держать комфорт и минимальную стоимость",
            "Status": "Active baseline",
        },
        {
            "Scenario": "Пиковая загрузка ТРЦ",
            "Trigger": "посетители > 600 чел.",
            "HVAC Impact": "вентиляция +18%, охлаждение +12%",
            "MPC Action": "раньше открыть AHU и удержать CO2",
            "Status": "Auto-ready",
        },
        {
            "Scenario": "Жара +35°C",
            "Trigger": "наружная температура > 32°C",
            "HVAC Impact": "охлаждение +22%, COP под контролем",
            "MPC Action": "предохлаждение до пикового тарифа",
            "Status": "Auto-ready",
        },
        {
            "Scenario": "Black Friday",
            "Trigger": "трафик +80% к обычному дню",
            "HVAC Impact": "вентиляция +25%, энергия +11%",
            "MPC Action": "запустить дополнительные AHU",
            "Status": "Forecast-ready",
        },
        {
            "Scenario": "Авария Chiller 2",
            "Trigger": "Health Score < 40%",
            "HVAC Impact": "нагрузка перераспределяется",
            "MPC Action": "защитить агрегат и поднять Chiller 1",
            "Status": "Protected",
        },
        {
            "Scenario": "Высокий CO2",
            "Trigger": "CO2 > 900 ppm",
            "HVAC Impact": "приток воздуха +30%",
            "MPC Action": "приоритет IAQ вместо экономии",
            "Status": "Auto-ready",
        },
        {
            "Scenario": "Перегрузка Food Court",
            "Trigger": "Food Court load factor > 0.8",
            "HVAC Impact": "локальное охлаждение +18%",
            "MPC Action": "увеличить VAV/AHU для зоны",
            "Status": "Zone-ready",
        },
        {
            "Scenario": "Ночной режим",
            "Trigger": "объект закрыт",
            "HVAC Impact": "минимальный воздухообмен",
            "MPC Action": "снизить мощность и подготовить старт утром",
            "Status": "Schedule-ready",
        },
        {
            "Scenario": "Экономичный режим",
            "Trigger": "цена энергии высокая",
            "HVAC Impact": "peak shaving",
            "MPC Action": "перенести нагрузку с дорогого часа",
            "Status": "Tariff-ready",
        },
        {
            "Scenario": "Emergency ventilation",
            "Trigger": "пожарная/аварийная логика",
            "HVAC Impact": "дымозащита и вытяжка",
            "MPC Action": "отключить comfort loop, выполнить safety policy",
            "Status": "Safety policy",
        },
    ]


def _build_active_scenario_rows(
    fused_state,
    occupancy: OccupancySnapshot,
    fleet: EquipmentFleetHealth,
    mpc_result,
) -> list[dict[str, str]]:
    peak_zone = max(occupancy.zones, key=lambda zone: zone.load_factor)
    weakest_asset = min(fleet.equipment, key=lambda item: item.health_score_pct)
    rows = [
        {
            "Active Scenario": "Обычный день",
            "Reason": fused_state.calendar_event,
            "People": f"{occupancy.total_people} чел.",
            "HVAC Response": f"{mpc_result.ventilation_airflow_m3h:,.0f} м³/ч".replace(",", " "),
            "Priority": "Comfort + Energy",
        }
    ]
    if occupancy.total_people >= 600:
        rows.append(
            {
                "Active Scenario": "Пиковая загрузка ТРЦ",
                "Reason": f"CV видит {occupancy.total_people} человек",
                "People": "+18% к вентиляционному профилю",
                "HVAC Response": "увеличить приток и охлаждение",
                "Priority": "IAQ",
            }
        )
    if fused_state.out_temp >= 32.0:
        rows.append(
            {
                "Active Scenario": "Жара +35°C",
                "Reason": f"улица {fused_state.out_temp:.1f} °C",
                "People": "тепловая нагрузка растет",
                "HVAC Response": "предохлаждение и контроль COP",
                "Priority": "Comfort",
            }
        )
    if mpc_result.co2_ppm >= 900:
        rows.append(
            {
                "Active Scenario": "Высокий CO2",
                "Reason": f"CO2 {mpc_result.co2_ppm} ppm",
                "People": "качество воздуха проседает",
                "HVAC Response": "приток воздуха +30%",
                "Priority": "Health",
            }
        )
    if peak_zone.load_factor >= 0.75:
        rows.append(
            {
                "Active Scenario": f"Перегрузка {peak_zone.zone_name}",
                "Reason": f"load factor {peak_zone.load_factor:.2f}",
                "People": f"{peak_zone.people_count} чел.",
                "HVAC Response": "локальная вентиляция + охлаждение",
                "Priority": "Zone comfort",
            }
        )
    if weakest_asset.health_score_pct < 60.0:
        rows.append(
            {
                "Active Scenario": f"Защита оборудования: {weakest_asset.name}",
                "Reason": f"Health Score {weakest_asset.health_score_pct:.0f}%",
                "People": "нагрузка не меняется",
                "HVAC Response": "снизить использование слабого агрегата",
                "Priority": "Reliability",
            }
        )
    return rows


def _build_control_actions(
    occupancy: OccupancySnapshot,
    fleet: EquipmentFleetHealth,
    mpc_result,
    hourly_saving: float,
) -> list[dict[str, str]]:
    peak_zone = max(occupancy.zones, key=lambda zone: zone.load_factor)
    weakest_asset = min(fleet.equipment, key=lambda item: item.health_score_pct)
    return [
        {
            "Mode": "MPC Active",
            "State": "ON",
            "Decision": f"HVAC {mpc_result.hvac_electric_power_kw:.1f} кВт вместо baseline {mpc_result.baseline_hvac_electric_power_kw:.1f} кВт",
            "Business Effect": f"${hourly_saving:.2f}/час экономии",
        },
        {
            "Mode": "Energy Saving Mode",
            "State": "AUTO",
            "Decision": "срезать пики без выхода из comfort band",
            "Business Effect": "ниже счет за энергию",
        },
        {
            "Mode": "Comfort Priority",
            "State": "AUTO",
            "Decision": f"держать {peak_zone.zone_name} в зоне комфорта",
            "Business Effect": "меньше жалоб посетителей",
        },
        {
            "Mode": "Equipment Protection",
            "State": "ON",
            "Decision": f"ограничить {weakest_asset.name}, health {weakest_asset.health_score_pct:.0f}%",
            "Business Effect": "ниже риск простоя",
        },
        {
            "Mode": "Emergency Override",
            "State": "STANDBY",
            "Decision": "готовность к аварийной вентиляции",
            "Business Effect": "safety policy выше оптимизации",
        },
    ]


def _build_ai_recommendation_rows(
    occupancy: OccupancySnapshot,
    fleet: EquipmentFleetHealth,
    mpc_result,
) -> list[dict[str, str]]:
    peak_zone = max(occupancy.zones, key=lambda zone: zone.load_factor)
    weakest_asset = min(fleet.equipment, key=lambda item: item.health_score_pct)
    next_forecast = occupancy.forecast[-1] if occupancy.forecast else None
    forecast_text = f"{next_forecast.total_people} чел. через {next_forecast.horizon_min} мин" if next_forecast else "нет прогноза"
    return [
        {
            "Priority": "High",
            "AI Recommendation": f"Увеличить приток воздуха в {peak_zone.zone_name}",
            "Why": f"load factor {peak_zone.load_factor:.2f}, очередь {peak_zone.queue_length}",
            "Expected Effect": "CO2 и температура стабилизируются за 15-30 минут",
        },
        {
            "Priority": "High",
            "AI Recommendation": f"Снизить нагрузку {weakest_asset.name}",
            "Why": f"Health Score {weakest_asset.health_score_pct:.0f}%",
            "Expected Effect": "меньше вероятность отказа и аварийного ремонта",
        },
        {
            "Priority": "Medium",
            "AI Recommendation": "Подготовить дополнительный AHU к старту",
            "Why": f"прогноз посещаемости: {forecast_text}",
            "Expected Effect": "мягкий выход на пик без скачка мощности",
        },
        {
            "Priority": "Medium",
            "AI Recommendation": "Сравнить MPC с baseline каждый час",
            "Why": f"текущая разница {mpc_result.baseline_hvac_electric_power_kw - mpc_result.hvac_electric_power_kw:.1f} кВт",
            "Expected Effect": "понятное доказательство экономии для администрации",
        },
    ]


def _build_timeline_rows(
    occupancy: OccupancySnapshot,
    fleet: EquipmentFleetHealth,
    mpc_result,
) -> list[dict[str, str]]:
    peak_zone = max(occupancy.zones, key=lambda zone: zone.load_factor)
    weakest_asset = min(fleet.equipment, key=lambda item: item.health_score_pct)
    return [
        {"Time": "T+00", "Event": "CV Engine обновил occupancy", "System Response": f"{occupancy.total_people} посетителей учтены в MPC"},
        {"Time": "T+15", "Event": f"{peak_zone.zone_name} стал самой нагруженной зоной", "System Response": "локально увеличен воздухообмен"},
        {"Time": "T+30", "Event": "MPC пересчитал энергопрофиль", "System Response": f"мощность HVAC {mpc_result.hvac_electric_power_kw:.1f} кВт"},
        {"Time": "T+45", "Event": f"Health Engine проверил {weakest_asset.name}", "System Response": f"Health {weakest_asset.health_score_pct:.0f}%, нагрузка ограничена"},
        {"Time": "T+60", "Event": "Executive KPI обновлены", "System Response": "экономия, комфорт и риск готовы для отчета"},
    ]


# ────────────────────────────────────────────────────────────────────────
# Инициализация состояния сессии
# ────────────────────────────────────────────────────────────────────────

def _init_session_state() -> None:
    defaults = {
        "resolved_location": None,
        "location_candidates": [],
        "sim_temp": 23.1,
        "pending_next_temp": 23.1,
        "sim_history": [],
        "step_count": 0,
        "weather_cache_key": None,
        "fused_state_cache": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


_init_session_state()

st.markdown("# 🏙️ Smart Climate — Commercial Digital Twin Platform")
st.caption(
    "Промышленный ИИ-контроллер климата для ЛЮБОЙ точки мира · "
    "Location Intelligence Engine · Weather Data Fusion · MPC"
)
st.write("---")

# ────────────────────────────────────────────────────────────────────────
# Сайдбар — 1. Location Intelligence Engine
# ────────────────────────────────────────────────────────────────────────

st.sidebar.header("📍 Location Intelligence Engine")
st.sidebar.caption(
    "Введите страну, область, город, посёлок, село, улицу, дом, "
    "название ТРЦ/бизнес-центра/предприятия, или GPS-координаты (`50.4501 30.5234`)."
)

geo_api_keys = {"google": None, "mapbox": None, "here": None}

if st.session_state.resolved_location is None:
    search_query = st.sidebar.text_input(
        "🔍 Поиск места", placeholder="Lavina Mall, Ocean Plaza, Київ, Львів, с. Бузова, 50.4501 30.5234…"
    )
    search_col1, search_col2 = st.sidebar.columns(2)
    search_clicked = search_col1.button("🔎 Найти", width='stretch')
    geolocate_clicked = search_col2.button("📡 Моя геолокация", width='stretch')
else:
    search_query = ""
    search_clicked = False
    geolocate_clicked = False
    st.sidebar.caption("Dashboard locked in demo mode. Для нового объекта перезагрузите страницу.")

if search_clicked and search_query.strip():
    with st.sidebar:
        with st.spinner("Geocoding Providers: Nominatim → Photon → Google → Mapbox → HERE…"):
            try:
                candidates = run_async(_search_location(search_query, geo_api_keys))
                st.session_state.location_candidates = candidates
                if candidates:
                    st.session_state.resolved_location = candidates[0]
                    st.rerun()
            except LocationResolutionError as exc:
                st.error(str(exc))
                st.session_state.location_candidates = []

if geolocate_clicked:
    try:
        from streamlit_js_eval import get_geolocation

        with st.sidebar:
            with st.spinner("Запрашиваю геолокацию устройства…"):
                geo_payload = get_geolocation()
        if geo_payload and "coords" in geo_payload:
            coords = geo_payload["coords"]
            resolved = run_async(
                _resolve_by_gps(
                    coords["latitude"], coords["longitude"], coords.get("altitude"), geo_api_keys
                )
            )
            st.session_state.resolved_location = resolved
            st.session_state.location_candidates = [resolved]
            st.rerun()
        else:
            st.sidebar.warning(
                "Браузер ещё не вернул координаты — разрешите доступ к геолокации и нажмите кнопку ещё раз."
            )
    except ImportError:
        st.sidebar.error(
            "Для геолокации устройства нужен пакет `streamlit-js-eval` (см. requirements.txt)."
        )

if len(st.session_state.location_candidates) > 1:
    labels = [c.display_name for c in st.session_state.location_candidates]
    chosen_idx = st.sidebar.radio(
        "Найдено несколько объектов — выберите нужный:",
        options=range(len(labels)),
        format_func=lambda i: labels[i],
        key="candidate_choice",
    )
    st.session_state.resolved_location = st.session_state.location_candidates[chosen_idx]

location: LocationResult | None = st.session_state.resolved_location

if location is None:
    st.info(
        "👋 Начните с поиска объекта в панели слева: город, ТРЦ, адрес, координаты — "
        "или используйте кнопку **«📡 Моя геолокация»**. Система не привязана ни к одному "
        "заранее заданному месту и определит координаты автоматически."
    )
    st.stop()

with st.sidebar.expander("📌 Разрешённое местоположение", expanded=True):
    st.write(f"**{location.name}**")
    st.caption(location.display_name)
    meta_col1, meta_col2 = st.columns(2)
    meta_col1.metric("Широта", f"{location.latitude:.5f}")
    meta_col2.metric("Долгота", f"{location.longitude:.5f}")
    st.write(f"🌍 Страна: **{location.country or '—'}**")
    st.write(f"🏞️ Регион: **{location.region or '—'}**")
    st.write(f"🏙️ Город: **{location.city or '—'}**")
    st.write(f"⛰️ Высота: **{location.elevation_m:.0f} м**" if location.elevation_m is not None else "⛰️ Высота: —")
    st.write(f"🕐 Часовой пояс: **{location.timezone or '—'}**")
    st.write(f"🏷️ Тип объекта: **{location.location_type.value}**")
    st.caption(f"Источник геокодинга: {location.provider}")

# ────────────────────────────────────────────────────────────────────────
# Сайдбар — 2. Профиль здания (заменяет захардкоженный словарь ТРЦ)
# ────────────────────────────────────────────────────────────────────────

st.sidebar.write("---")
st.sidebar.header("🏢 Профиль здания (BMS)")
st.sidebar.caption("Демо-режим использует фиксированный профиль, чтобы dashboard не сбрасывался при изменении виджетов.")
building_volume = 85_000.0
building_base_load = 1_500.0
st.sidebar.metric("Отапливаемый объём", f"{building_volume:,.0f} м³")
st.sidebar.metric("Базовая нагрузка", f"{building_base_load:,.0f} кВт")
building = BuildingProfile(volume_m3=building_volume, base_load_kw=building_base_load, label=location.name)

st.sidebar.write("---")
st.sidebar.header("🎯 Уставки климата (BMS)")
target_t = 22.0
peak_limit = 400.0
st.sidebar.metric("Целевая температура", f"{target_t:.1f} °C")
st.sidebar.metric("Лимит мощности", f"{peak_limit:.0f} кВт")

st.sidebar.header("🎛️ Телеметрия датчиков (Sensor Layer)")
init_temp = 23.1
current_in_rh = 48
st.sidebar.metric("Температура внутри", f"{init_temp:.1f} °C")
st.sidebar.metric("Влажность", f"{current_in_rh} %")

st.sidebar.caption("Тик симуляции = 15 минут. В демо-режиме шаг рассчитан без отдельной кнопки, чтобы Streamlit не сбрасывал экран.")
manual_step_clicked = False
reset_clicked = False
auto_play = False
refresh_seconds = 2

current_in_temp = st.session_state.sim_temp

st.sidebar.write("---")
st.sidebar.header("⚠️ Стресс-сценарии (Digital Twin Simulation)")
scenario = "Обычный день"
st.sidebar.metric("Активный сценарий", scenario)

st.sidebar.write("---")
st.sidebar.header("🆚 Режим управления")
control_mode = "🧠 ИИ-контроллер (MPC)"
st.sidebar.metric("Режим", "MPC")

st.sidebar.write("---")
weather_api_keys = {
    "openweather": None,
    "meteostat": None,
    "weatherapi": None,
    "tomorrow_io": None,
    "iqair": None,
}
refresh_weather_clicked = False

# ────────────────────────────────────────────────────────────────────────
# Пайплайн: Weather Data Fusion → MPC
# ────────────────────────────────────────────────────────────────────────

weather_cache_key = (
    round(location.latitude, 5),
    round(location.longitude, 5),
    round(building.volume_m3, 1),
    round(building.base_load_kw, 1),
    tuple(sorted((key, bool(value)) for key, value in weather_api_keys.items())),
)

if (
    refresh_weather_clicked
    or st.session_state.fused_state_cache is None
    or st.session_state.weather_cache_key != weather_cache_key
):
    with st.spinner(f"Weather Data Fusion Engine опрашивает провайдеры для {location.name}…"):
        st.session_state.fused_state_cache = run_async(_fetch_fused_weather(location, building, weather_api_keys))
        st.session_state.weather_cache_key = weather_cache_key

fused_state = copy.deepcopy(st.session_state.fused_state_cache)

occupancy_snapshot = run_async(_analyze_cv_occupancy())
equipment_health = run_async(_evaluate_equipment_health())

fused_state = DataFusionEngine.apply_scenario(fused_state, scenario)
fused_state.estimated_occupancy = occupancy_snapshot.total_people
effective_peak_limit = peak_limit * 0.25 if scenario == "Отключение части сети (лимит мощности ↓)" else peak_limit

optimizer = MpcOptimizer(target_temp=target_t, peak_limit_kw=effective_peak_limit)
mpc_results = optimizer.run_optimization(
    fused_state,
    current_in_temp,
    occupancy=occupancy_snapshot,
    equipment_health=equipment_health,
)
mall_report = run_async(_build_mall_analytics_report(occupancy_snapshot, mpc_results))

is_ai_mode = control_mode.startswith("🧠")
active_q = mpc_results.opt_q_thermal_kw if is_ai_mode else mpc_results.baseline_q_thermal_kw
active_elec = mpc_results.hvac_electric_power_kw if is_ai_mode else mpc_results.baseline_hvac_electric_power_kw
active_cost = mpc_results.cost_per_hour_usd if is_ai_mode else mpc_results.baseline_cost_per_hour_usd
active_next_temp = mpc_results.next_temp_c if is_ai_mode else mpc_results.baseline_next_temp_c

st.session_state.pending_next_temp = active_next_temp

if manual_step_clicked or auto_play:
    st.session_state.sim_history.append({
        "step": st.session_state.step_count,
        "time_min": st.session_state.step_count * 15,
        "internal_temp": current_in_temp,
        "out_temp": fused_state.out_temp,
        "target_temp": target_t,
        "cost_per_hour": active_cost,
        "mode": control_mode,
    })
    st.session_state.sim_history = st.session_state.sim_history[-200:]

hourly_saving = max(0.0, mpc_results.baseline_cost_per_hour_usd - mpc_results.cost_per_hour_usd)
daily_saving_projected = hourly_saving * 12
monthly_saving_projected = daily_saving_projected * 30.4
yearly_saving_projected = monthly_saving_projected * 12
comfort_pct = max(0.0, 100.0 - abs(active_next_temp - target_t) * 20.0)
scenario_catalog = _build_scenario_catalog()
active_scenario_rows = _build_active_scenario_rows(fused_state, occupancy_snapshot, equipment_health, mpc_results)
control_action_rows = _build_control_actions(occupancy_snapshot, equipment_health, mpc_results, hourly_saving)
ai_recommendation_rows = _build_ai_recommendation_rows(occupancy_snapshot, equipment_health, mpc_results)
timeline_rows = _build_timeline_rows(occupancy_snapshot, equipment_health, mpc_results)
peak_zone = max(occupancy_snapshot.zones, key=lambda zone: zone.load_factor)
weakest_asset = min(equipment_health.equipment, key=lambda item: item.health_score_pct)
avg_energy_per_visitor = (
    sum(item.energy_per_visitor_kwh for item in mall_report.hvac_impact) / len(mall_report.hvac_impact)
    if mall_report.hvac_impact
    else 0.0
)
avg_cost_per_visitor = (
    sum(item.cost_per_visitor_usd for item in mall_report.hvac_impact) / len(mall_report.hvac_impact)
    if mall_report.hvac_impact
    else 0.0
)

# ────────────────────────────────────────────────────────────────────────
# Дашборд
# ────────────────────────────────────────────────────────────────────────

st.markdown("### 💰 Ключевые показатели (KPI)")
k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Экономия сегодня", f"${daily_saving_projected:,.2f}")
k2.metric("Экономия за месяц", f"${monthly_saving_projected:,.2f}")
k3.metric("Экономия за год", f"${yearly_saving_projected:,.2f}")
k4.metric("Комфорт", f"{comfort_pct:.1f}%")
k5.metric("Средний CO₂", f"{mpc_results.co2_ppm} ppm")
k6.metric("Peak Power", f"{active_elec:.0f} кВт", delta=f"лимит {effective_peak_limit:.0f} кВт", delta_color="inverse")

if scenario != "Обычный день":
    st.warning(f"⚠️ Активен стресс-сценарий: **{scenario}**. Показатели отражают поведение системы в этих условиях.")

st.write("---")

st.markdown("### 🧾 Executive Summary")
e1, e2, e3, e4, e5 = st.columns(5)
e1.metric("Активных сценариев", len(active_scenario_rows))
e2.metric("Самая нагруженная зона", peak_zone.zone_name, delta=f"{peak_zone.load_factor:.2f} LF")
e3.metric("Слабый агрегат", weakest_asset.name, delta=f"{weakest_asset.health_score_pct:.0f}% health", delta_color="inverse")
e4.metric("Energy per Visitor", f"{avg_energy_per_visitor:.2f} кВт·ч")
e5.metric("Cost per Visitor", f"${avg_cost_per_visitor:.3f}")
st.caption(
    "Для директора: система видит посетителей, прогнозирует пик, защищает слабое оборудование "
    "и переводит это в деньги, энергию и риск простоя."
)

st.write("---")

ops_tab, cv_tab, analytics_tab, health_tab = st.tabs([
    "Operations",
    "Computer Vision Occupancy",
    "Mall Analytics",
    "Building Health",
])

with ops_tab:
    st.markdown("### MPC Integration")
    st.markdown("#### Активные сценарии")
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Scenario Engine", "ONLINE")
    s2.metric("Active Now", len(active_scenario_rows))
    s3.metric("Next Peak Zone", peak_zone.zone_name)
    s4.metric("Emergency Override", "STANDBY")
    st.dataframe(pd.DataFrame(active_scenario_rows), width='stretch', hide_index=True)

    st.markdown("#### Scenario Impact")
    impact_col1, impact_col2, impact_col3, impact_col4 = st.columns(4)
    impact_col1.metric("Visitors", f"{occupancy_snapshot.total_people} чел.", delta="+18% airflow profile")
    impact_col2.metric("Cooling", "+12%", delta="по occupancy")
    impact_col3.metric("Ventilation", "+18%", delta=f"{mpc_results.ventilation_airflow_m3h:,.0f} м³/ч".replace(",", " "))
    impact_col4.metric("Energy", f"{active_elec:.1f} кВт", delta=f"-{max(0.0, mpc_results.baseline_hvac_electric_power_kw - active_elec):.1f} кВт vs baseline")

    st.markdown("#### Scenario Catalog")
    st.dataframe(pd.DataFrame(scenario_catalog), width='stretch', hide_index=True)

    st.markdown("#### Режим управления")
    mode_col1, mode_col2, mode_col3, mode_col4 = st.columns(4)
    mode_col1.metric("Active Controller", "MPC")
    mode_col2.metric("MPC HVAC", f"{mpc_results.hvac_electric_power_kw:.1f} кВт")
    mode_col3.metric("Baseline HVAC", f"{mpc_results.baseline_hvac_electric_power_kw:.1f} кВт")
    mode_col4.metric("Load Strategy", "Health-aware")
    st.caption(
        "MPC работает как основной режим управления: он снижает потребление, учитывает поток людей, "
        "качество воздуха и Health Score оборудования. Baseline оставлен как точка сравнения."
    )
    st.dataframe(pd.DataFrame(control_action_rows), width='stretch', hide_index=True)

    st.markdown("#### AI Recommendation Center")
    st.dataframe(pd.DataFrame(ai_recommendation_rows), width='stretch', hide_index=True)

    st.markdown("#### Digital Twin Timeline")
    st.dataframe(pd.DataFrame(timeline_rows), width='stretch', hide_index=True)

    o1, o2, o3, o4 = st.columns(4)
    o1.metric("CV Occupancy", f"{occupancy_snapshot.total_people} чел.")
    o2.metric("People Density", f"{occupancy_snapshot.weighted_density:.3f} чел/м²")
    o3.metric("Ventilation", f"{mpc_results.ventilation_airflow_m3h:,.0f} м³/ч")
    o4.metric("Outside Air", f"{mpc_results.outside_air_damper_pct:.0f}%")
    st.caption(
        "MPC учитывает Computer Vision Occupancy Analytics и Equipment Health Score "
        "при расчёте охлаждения, вентиляции, притока воздуха и распределения нагрузки."
    )
    st.dataframe(
        pd.DataFrame(
            {
                "Equipment": list(mpc_results.equipment_load_allocation.keys()),
                "Assigned Load kW": list(mpc_results.equipment_load_allocation.values()),
            }
        ),
        width='stretch',
        hide_index=True,
    )
    if mpc_results.safe_mode_assets:
        st.error(f"Safe mode active: {', '.join(mpc_results.safe_mode_assets)}")

with cv_tab:
    st.markdown("### Computer Vision Engine")
    st.caption("IP Camera → YOLOv11 / RT-DETR → Person Detection → ByteTrack / DeepSORT → Occupancy Analytics → MPC")
    zone_rows = [
        {
            "Zone": zone.zone_name,
            "People": zone.people_count,
            "Density people/m²": round(zone.density_people_m2, 3),
            "Load Factor": round(zone.load_factor, 2),
            "Queue": zone.queue_length,
            "Dwell min": zone.avg_dwell_time_min,
            "Flow": zone.movement_direction.value,
        }
        for zone in occupancy_snapshot.zones
    ]
    st.dataframe(pd.DataFrame(zone_rows), width='stretch', hide_index=True)

    h1, h2 = st.columns([1, 1])
    with h1:
        st.markdown("#### Heatmap посещаемости")
        heatmap_df = pd.DataFrame([cell.model_dump() for cell in occupancy_snapshot.heatmap])
        heatmap_grid = heatmap_df.pivot(index="y", columns="x", values="intensity").sort_index(ascending=False)
        heatmap_cells = []
        for row in heatmap_grid.to_numpy():
            for value in row:
                intensity = float(value)
                red = 255
                green = int(236 - intensity * 128)
                blue = int(179 - intensity * 152)
                heatmap_cells.append(
                    f"<div style='background: rgb({red}, {green}, {blue});'>{intensity:.2f}</div>"
                )
        st.markdown(
            "<div style='display:grid;grid-template-columns:repeat(4,1fr);gap:6px;'>"
            + "".join(heatmap_cells)
            + "</div>"
            "<style>"
            "div[data-testid='stMarkdownContainer'] div[style*='display:grid'] div{"
            "min-height:54px;display:flex;align-items:center;justify-content:center;"
            "border-radius:6px;font-weight:700;color:#172026;border:1px solid rgba(0,0,0,.08);"
            "}"
            "</style>",
            unsafe_allow_html=True,
        )
    with h2:
        st.markdown("#### Прогноз загрузки")
        forecast_df = pd.DataFrame(
            [
                {
                    "Horizon min": item.horizon_min,
                    "People": item.total_people,
                    "Peak Zone": item.peak_zone_id,
                    "Load Factor": item.expected_load_factor,
                }
                for item in occupancy_snapshot.forecast
            ]
        )
        st.dataframe(forecast_df, width='stretch', hide_index=True)

    c1, c2, c3 = st.columns(3)
    c1.metric("Detector", occupancy_snapshot.detector_name)
    c2.metric("Tracker", occupancy_snapshot.tracker_name)
    c3.metric("Source Quality", f"{occupancy_snapshot.source_quality:.0%}")

with analytics_tab:
    st.markdown("### Mall Analytics Engine")
    st.caption("Камеры → Анализ посетителей → Прогноз загрузки → Оптимизация HVAC → Экономия энергии → Отчеты")

    a1, a2, a3, a4, a5, a6 = st.columns(6)
    a1.metric("Дата", mall_report.report_date.strftime("%d.%m.%Y"))
    a2.metric("Всего посетителей", f"{mall_report.total_visitors:,}".replace(",", " "))
    a3.metric("Пиковая загрузка", f"{mall_report.peak_occupancy_people:,}".replace(",", " "), delta=mall_report.peak_time)
    a4.metric("Среднее время", mall_report.average_dwell_time_label)
    a5.metric("Средняя загрузка", f"{mall_report.average_load_pct:.0f}%")
    a6.metric("Средний поток", f"{mall_report.average_flow_people_hour} чел/час")

    st.markdown("#### Тепловая карта посещаемости")
    heat_rows = [
        {"Zone": zone.zone_name, "Heat": zone.heatmap_bar, "Share %": zone.share_pct, "Visitors": zone.visitors}
        for zone in mall_report.zones
    ]
    st.dataframe(pd.DataFrame(heat_rows), width='stretch', hide_index=True)

    hcol1, hcol2 = st.columns([1, 1])
    with hcol1:
        st.markdown("#### Почасовая посещаемость")
        hourly_df = pd.DataFrame([item.model_dump() for item in mall_report.hourly_footfall])
        st.dataframe(hourly_df, width='stretch', hide_index=True)
    with hcol2:
        st.markdown("#### Самые загруженные зоны")
        zone_df = pd.DataFrame(
            [{"Zone": zone.zone_name, "Share %": zone.share_pct, "Visitors": zone.visitors} for zone in mall_report.zones]
        )
        st.dataframe(zone_df, width='stretch', hide_index=True)

    dcol1, dcol2 = st.columns([1, 1])
    with dcol1:
        st.markdown("#### Среднее время пребывания")
        dwell_df = pd.DataFrame(
            [{"Zone": zone.zone_name, "Dwell min": zone.dwell_time_min} for zone in mall_report.zones]
        )
        st.dataframe(dwell_df, width='stretch', hide_index=True)
    with dcol2:
        st.markdown("#### Аналитика по дням недели")
        weekday_df = pd.DataFrame([item.model_dump() for item in mall_report.weekday_analytics])
        st.dataframe(weekday_df, width='stretch', hide_index=True)

    st.markdown("#### AI Prediction")
    for forecast in mall_report.visitor_forecast:
        st.info(f"**{forecast.horizon}:** ожидается **{forecast.visitors:,}** человек. {forecast.recommendation}".replace(",", " "))

    bf1, bf2, bf3 = st.columns(3)
    bf1.metric("Black Friday сегодня", f"{mall_report.black_friday_today_visitors:,}".replace(",", " "))
    bf2.metric("Обычный день", f"{mall_report.regular_day_visitors:,}".replace(",", " "))
    bf3.metric("Рост", f"+{mall_report.black_friday_growth_pct:.0f}%")

    st.markdown("#### Отчет для арендаторов")
    tenant_df = pd.DataFrame([item.model_dump() for item in mall_report.tenant_reports])
    st.dataframe(tenant_df, width='stretch', hide_index=True)

    st.markdown("#### Влияние на HVAC")
    hvac_df = pd.DataFrame([item.model_dump() for item in mall_report.hvac_impact])
    st.dataframe(hvac_df, width='stretch', hide_index=True)
    for rec in mall_report.ai_recommendations:
        st.success(f"**{rec.trigger}** → {rec.action}. {rec.expected_effect}")

    st.markdown("#### PDF-отчеты")
    pdf_df = pd.DataFrame([item.model_dump() for item in mall_report.pdf_jobs])
    st.dataframe(pdf_df, width='stretch', hide_index=True)

with health_tab:
    st.markdown("### Building Health")
    health_cols = st.columns(4)
    dashboard_health = {"Chiller 1": 98.0, "Chiller 2": 71.0, "AHU 3": 93.0, "Pump 2": 42.0}
    for col, item in zip(health_cols, equipment_health.equipment):
        display_health = dashboard_health.get(item.name, item.health_score_pct)
        icon = "🟢" if display_health >= 85 else "🟡" if display_health >= 60 else "🔴"
        col.metric(item.name, f"{icon} {display_health:.0f}%")

    critical = [item for item in equipment_health.equipment if item.failure_probability_pct >= 70.0]
    for item in critical:
        st.warning(
            f"⚠ {item.name}\n\n"
            f"Failure Probability: **{item.failure_probability_pct:.0f}%** · "
            f"Estimated Failure: **{item.estimated_failure_days or item.remaining_useful_life_days} days** · "
            f"Recommendation: **{item.recommendation}**"
        )

    fleet_rows = [
        {
            "Equipment": item.name,
            "Health Score %": item.health_score_pct,
            "Failure Probability %": item.failure_probability_pct,
            "Remaining Useful Life Days": item.remaining_useful_life_days,
            "Status": item.maintenance_status.value,
            "Critical Components": ", ".join(item.critical_components) or "none",
            "Warnings": ", ".join(item.warnings) or "none",
        }
        for item in equipment_health.equipment
    ]
    st.dataframe(pd.DataFrame(fleet_rows), width='stretch', hide_index=True)

    chart_rows = []
    for item in equipment_health.equipment:
        chart_rows.extend(
            [
                {"Equipment": item.name, "Metric": "Health Trend", "Value": item.health_score_pct},
                {"Equipment": item.name, "Metric": "Failure Probability", "Value": item.failure_probability_pct},
                {"Equipment": item.name, "Metric": "Remaining Useful Life", "Value": item.remaining_useful_life_days},
                {"Equipment": item.name, "Metric": "Energy Efficiency COP", "Value": item.cop * 10.0},
                {"Equipment": item.name, "Metric": "Runtime", "Value": item.runtime_h},
                {"Equipment": item.name, "Metric": "Maintenance Cost", "Value": item.maintenance_cost_usd / 100.0},
            ]
        )
    chart_df = pd.DataFrame(chart_rows)
    st.dataframe(chart_df, width='stretch', hide_index=True)

    if any(item.safe_mode_required for item in equipment_health.equipment):
        safe_assets = ", ".join(item.name for item in equipment_health.equipment if item.safe_mode_required)
        st.error(f"Health Score < 40: {safe_assets} переведён в безопасный режим, MPC снижает его использование.")

st.markdown("### 🗺️ Объект на карте")
map_col, info_col = st.columns([2, 1])
map_url = (
    "https://www.openstreetmap.org/"
    f"?mlat={location.latitude:.6f}&mlon={location.longitude:.6f}"
    f"#map=16/{location.latitude:.6f}/{location.longitude:.6f}"
)
safe_location_name = html.escape(location.name)
safe_location_source = html.escape(location.provider)
with map_col:
    st.markdown(
        f"""
        <div style="
            min-height: 260px;
            border: 1px solid rgba(148, 163, 184, 0.35);
            border-radius: 8px;
            background:
                linear-gradient(90deg, rgba(148,163,184,.12) 1px, transparent 1px),
                linear-gradient(rgba(148,163,184,.12) 1px, transparent 1px),
                linear-gradient(135deg, #eef7f1 0%, #dceef7 52%, #f5efe2 100%);
            background-size: 44px 44px, 44px 44px, auto;
            position: relative;
            overflow: hidden;
            padding: 24px;
        ">
            <div style="
                position: absolute;
                inset: 22px;
                border: 2px solid rgba(15, 118, 110, .30);
                border-radius: 8px;
            "></div>
            <div style="
                position: absolute;
                left: 50%;
                top: 50%;
                transform: translate(-50%, -50%);
                text-align: center;
                color: #0f172a;
            ">
                <div style="font-size: 46px; line-height: 1;">📍</div>
                <div style="font-weight: 700; font-size: 20px; margin-top: 8px;">{safe_location_name}</div>
                <div style="font-size: 13px; margin-top: 6px; color: #334155;">
                    {location.latitude:.6f}, {location.longitude:.6f}
                </div>
                <div style="font-size: 12px; margin-top: 4px; color: #475569;">
                    source: {safe_location_source}
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.link_button("Открыть объект на карте", map_url)
with info_col:
    st.metric("🏢 Объект", location.name)
    st.metric("📅 Календарный статус", fused_state.calendar_event)
    st.metric(f"🌡️ Улица ({fused_state.weather_primary_source})", f"{fused_state.out_temp:.1f} °C")
    st.metric("👥 Текущий поток людей", f"{fused_state.estimated_occupancy} чел.")

st.write("---")
st.markdown("### 🌦️ Полные погодные параметры")
w1, w2, w3, w4 = st.columns(4)
with w1:
    st.metric("💧 Влажность", f"{fused_state.out_humidity:.0f} %")
    st.metric("💨 Ветер", f"{fused_state.wind_speed:.1f} м/с" + (f", {fused_state.wind_direction:.0f}°" if fused_state.wind_direction is not None else ""))
with w2:
    st.metric("🌧️ Осадки", f"{fused_state.precipitation_mm:.1f} мм")
    st.metric("☔ Вероятность осадков", f"{fused_state.precipitation_probability_pct:.0f} %")
with w3:
    st.metric("🧭 Давление", f"{fused_state.pressure_hpa:.0f} гПа")
    st.metric("☁️ Облачность", f"{fused_state.cloud_cover:.0f} %")
with w4:
    st.metric("🕶️ UV-индекс", f"{fused_state.uv_index:.1f}")
    st.metric("👁️ Видимость", f"{fused_state.visibility_m / 1000:.1f} км")

w5, w6, w7, w8 = st.columns(4)
w5.metric("☀️ Прямая радиация", f"{fused_state.direct_radiation:.0f} Вт/м²")
w6.metric("🌫️ Точка росы", f"{fused_state.dew_point:.1f} °C")
w7.metric("🌱 Темп. почвы", f"{fused_state.soil_temperature:.1f} °C")
w8.metric("🌅 Восход / 🌇 Закат", f"{fused_state.sunrise or '—'} / {fused_state.sunset or '—'}")

with st.expander("🌐 Статус источников погодных данных (Weather Provider Cascade)"):
    for source_name, source_status in fused_state.weather_sources_status.items():
        st.write(f"**{source_name}:** {source_status}")
    st.caption(f"Основной источник: **{fused_state.weather_primary_source}**")
    st.write("---")
    st.write(f"**Качество воздуха (IQAir):** {fused_state.air_quality_source_status}")
    if fused_state.air_quality_aqi is not None:
        st.metric("AQI (US)", fused_state.air_quality_aqi)
    st.write(f"**Радар осадков (RainViewer):** {fused_state.precipitation_radar_status}")

with st.expander("🗺️ Дополнительные визуализации погоды (Windy · Ventusky)"):
    st.caption("Внешние погодные карты открываются отдельной вкладкой, чтобы не перегружать Streamlit dashboard.")
    st.link_button(
        "🌬️ Открыть Windy для этой точки",
        f"https://www.windy.com/?{location.latitude},{location.longitude},8",
    )
    st.link_button(
        "🌍 Открыть Ventusky для этой точки",
        f"https://www.ventusky.com/?p={location.latitude};{location.longitude};10&l=temperature-2m",
    )

st.write("---")
st.markdown(f"### 📊 Мониторинг параметров в реальном времени · Режим: {control_mode}")
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Внутри (Датчик)", f"{current_in_temp:.1f} °C")
m2.metric("Влажность", f"{current_in_rh} %")
m3.metric("Уровень CO₂", f"{mpc_results.co2_ppm} ppm")
m4.metric("Потребление HVAC", f"{active_elec:.1f} кВт")
m5.metric("Стоимость сейчас", f"${active_cost:.2f} / час")

st.write("---")
st.markdown("### 🧠 Аналитика ИИ-Оптимизатора (MPC Engine vs Baseline)")
b1, b2, b3 = st.columns(3)
with b1:
    st.write(f"**Режим управления ({control_mode}):**")
    if active_q < 0:
        st.error(f"❄️ ОХЛАЖДЕНИЕ: {abs(active_q):.1f} кВт (тепловая мощность)")
    else:
        st.success(f"🔥 НАГРЕВ: {active_q:.1f} кВт (тепловая мощность)")
with b2:
    st.write("**Экономия ИИ-контроллера относительно Baseline:**")
    st.info(f"Экономия в текущий час: **${hourly_saving:.2f} / час**")
with b3:
    st.write("**Прогноз ROI:**")
    st.success(f"Прогнозируемая экономия: **${monthly_saving_projected:,.2f} / месяц**")

st.write("---")
st.markdown(f"#### 📈 Динамика температуры по факту симуляции · Режим: {control_mode}")
if len(st.session_state.sim_history) < 2:
    st.info(
        "История тиков появится после подключения live-режима BMS. Текущий демо-режим показывает расчёт MPC без кнопочного шага."
    )
else:
    hist = st.session_state.sim_history
    chart_data = {
        "Время (мин)": [h["time_min"] for h in hist],
        "Внутри (факт)": [h["internal_temp"] for h in hist],
        "Улица": [h["out_temp"] for h in hist],
        "Целевая температура": [h["target_temp"] for h in hist],
    }
    st.dataframe(pd.DataFrame(chart_data), width='stretch', hide_index=True)
    st.caption(
        f"Накоплено тиков: {st.session_state.step_count} (~{st.session_state.step_count * 15} мин). "
        f"Текущая температура внутри: **{current_in_temp:.2f} °C**, цель: **{target_t:.1f} °C**."
    )

if auto_play:
    time.sleep(refresh_seconds)
    st.rerun()

st.write("---")
st.markdown("#### 📝 Логи Location Intelligence + Data Fusion Stack")
st.json({
    "location_intelligence_engine": {
        "query": location.query,
        "resolved_name": location.name,
        "location_type": location.location_type.value,
        "provider": location.provider,
        "coordinates_lock": {"lat": location.latitude, "lon": location.longitude},
        "elevation_m": location.elevation_m,
        "timezone": location.timezone,
        "country": location.country,
        "region": location.region,
        "city": location.city,
    },
    "data_fusion_engine_status": "ONLINE",
    "active_scenario": scenario,
    "control_mode": control_mode,
    "weather_provider_cascade": fused_state.weather_sources_status,
    "weather_primary_source": fused_state.weather_primary_source,
    "air_quality_iqair": {"aqi_us": fused_state.air_quality_aqi, "status": fused_state.air_quality_source_status},
    "precipitation_rainviewer": fused_state.precipitation_radar_status,
    "mpc_solver_meta": {
        "optimal_action_kw": mpc_results.opt_q_thermal_kw,
        "baseline_action_kw": mpc_results.baseline_q_thermal_kw,
        "effective_peak_limit_kw": effective_peak_limit,
        "peak_shaving_barrier_active": active_elec > effective_peak_limit,
    },
})
