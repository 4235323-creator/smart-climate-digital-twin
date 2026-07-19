"""Математическое ядро MPC (векторная оптимизация с учётом износа и теплофизики здания)."""
from __future__ import annotations

from dataclasses import dataclass

from scipy.optimize import minimize

from ..equipment.models import EquipmentFleetHealth
from ..vision.models import OccupancySnapshot
from ..weather.models import FusedDataState


@dataclass(slots=True)
class MpcResult:
    opt_q_thermal_kw: float
    hvac_electric_power_kw: float
    cost_per_hour_usd: float
    next_temp_c: float
    baseline_q_thermal_kw: float
    baseline_hvac_electric_power_kw: float
    baseline_cost_per_hour_usd: float
    baseline_next_temp_c: float
    co2_ppm: int
    ventilation_airflow_m3h: float
    outside_air_damper_pct: float
    cooling_boost_kw: float
    equipment_load_allocation: dict[str, float]
    safe_mode_assets: tuple[str, ...]


class MpcOptimizer:
    """Model Predictive Control шаг для HVAC — не зависит от того, какое здание оптимизируется."""

    def __init__(self, target_temp: float = 22.0, peak_limit_kw: float = 500.0) -> None:
        self.target_temp = target_temp
        self.peak_limit_kw = peak_limit_kw
        self.cop_cooling = 3.2
        self.cop_heating = 3.6

    def run_optimization(
        self,
        state: FusedDataState,
        current_internal_temp: float,
        occupancy: OccupancySnapshot | None = None,
        equipment_health: EquipmentFleetHealth | None = None,
    ) -> MpcResult:
        effective_occupancy = occupancy.total_people if occupancy is not None else state.estimated_occupancy
        occupancy_load_factor = occupancy.max_load_factor if occupancy is not None else 0.0
        people_heat_gain = effective_occupancy * 0.10  # 100 Вт на человека
        cooling_boost_kw = self._cooling_boost(occupancy_load_factor, effective_occupancy)
        wind_factor = 1.0 + (state.wind_speed * 0.08)
        total_solar_gain = (
            state.direct_radiation * (1.0 - (state.cloud_cover / 100.0)) + state.diffuse_radiation
        ) * 0.05

        def next_temp(q: float) -> float:
            dT = (
                q
                - cooling_boost_kw
                + people_heat_gain
                + total_solar_gain
                + (state.out_temp - current_internal_temp) * wind_factor / 2.0
            ) / 50.0 * 0.25
            return current_internal_temp + dT

        def cost_function(q_hvac: list[float]) -> float:
            q = q_hvac[0]
            cop = self.cop_heating if q >= 0 else self.cop_cooling
            elec_power = abs(q) / cop

            energy_cost = elec_power * state.electricity_price_usd_kwh
            comfort_penalty = ((next_temp(q) - self.target_temp) ** 2) * 450.0
            peak_penalty = max(0.0, elec_power - self.peak_limit_kw) ** 2 * 1000.0
            wear_penalty = (q ** 2) * self._fleet_wear_factor(equipment_health)

            return energy_cost + comfort_penalty + peak_penalty + wear_penalty

        res = minimize(cost_function, [0.0], method="L-BFGS-B", bounds=[(-800.0, 800.0)])
        opt_q = float(res.x[0])
        opt_cop = self.cop_heating if opt_q >= 0 else self.cop_cooling
        opt_elec = abs(opt_q) / opt_cop

        # Baseline: обычный термостат без предсказания тарифа/солнца/ветра.
        baseline_q = max(-800.0, min(800.0, -(current_internal_temp - self.target_temp) * 80.0))
        baseline_cop = self.cop_heating if baseline_q >= 0 else self.cop_cooling
        baseline_elec = abs(baseline_q) / baseline_cop
        ventilation_airflow = self._ventilation_airflow(effective_occupancy, occupancy_load_factor)
        outside_air_damper = min(100.0, 35.0 + occupancy_load_factor * 45.0)
        allocation = self._allocate_equipment_load(opt_elec, equipment_health)
        safe_mode_assets = tuple(
            item.name for item in equipment_health.equipment if item.safe_mode_required
        ) if equipment_health is not None else ()

        return MpcResult(
            opt_q_thermal_kw=opt_q,
            hvac_electric_power_kw=opt_elec,
            cost_per_hour_usd=opt_elec * state.electricity_price_usd_kwh,
            next_temp_c=next_temp(opt_q),
            baseline_q_thermal_kw=baseline_q,
            baseline_hvac_electric_power_kw=baseline_elec,
            baseline_cost_per_hour_usd=baseline_elec * state.electricity_price_usd_kwh,
            baseline_next_temp_c=next_temp(baseline_q),
            co2_ppm=450 + int(effective_occupancy * 0.08),
            ventilation_airflow_m3h=ventilation_airflow,
            outside_air_damper_pct=outside_air_damper,
            cooling_boost_kw=cooling_boost_kw,
            equipment_load_allocation=allocation,
            safe_mode_assets=safe_mode_assets,
        )

    @staticmethod
    def _cooling_boost(load_factor: float, occupancy: int) -> float:
        if load_factor < 0.55:
            return 0.0
        return min(180.0, occupancy * 0.045 * load_factor)

    @staticmethod
    def _ventilation_airflow(occupancy: int, load_factor: float) -> float:
        base_airflow = occupancy * 38.0
        demand_boost = 1.0 + min(0.45, load_factor * 0.28)
        return round(base_airflow * demand_boost, 1)

    @staticmethod
    def _fleet_wear_factor(equipment_health: EquipmentFleetHealth | None) -> float:
        if equipment_health is None:
            return 0.02
        health_penalty = max(0.0, 80.0 - equipment_health.average_health_score) / 80.0
        return 0.02 + health_penalty * 0.045

    @staticmethod
    def _allocate_equipment_load(
        target_power_kw: float, equipment_health: EquipmentFleetHealth | None
    ) -> dict[str, float]:
        if equipment_health is None or not equipment_health.equipment:
            return {"HVAC Fleet": round(target_power_kw, 1)}

        weights: dict[str, float] = {}
        for item in equipment_health.equipment:
            if item.safe_mode_required:
                weight = 0.05
            else:
                weight = max(0.1, item.health_score_pct / 100.0)
            if item.equipment_type.value not in {"chiller", "ahu", "pump"}:
                weight *= 0.5
            weights[item.name] = weight

        total_weight = sum(weights.values()) or 1.0
        return {
            name: round(target_power_kw * weight / total_weight, 1)
            for name, weight in weights.items()
        }
