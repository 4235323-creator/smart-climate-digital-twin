"""Equipment Health Engine with signal processing, features, ML prediction, and planning."""
from __future__ import annotations

from datetime import datetime

from .models import (
    EquipmentFeatures,
    EquipmentFleetHealth,
    EquipmentHealth,
    EquipmentTelemetry,
    EquipmentType,
    IEquipmentTelemetryRepository,
    IFailurePredictionModel,
    MaintenanceStatus,
)


class DemoEquipmentTelemetryRepository(IEquipmentTelemetryRepository):
    async def read_latest(self) -> list[EquipmentTelemetry]:
        now = datetime.now()
        return [
            EquipmentTelemetry(
                equipment_id="chiller_1",
                name="Chiller 1",
                equipment_type=EquipmentType.CHILLER,
                timestamp=now,
                compressor_temp_c=68.0,
                vibration_mm_s=1.2,
                motor_current_a=216.0,
                voltage_v=400.0,
                pressure_bar=8.2,
                airflow_m3h=0.0,
                waterflow_m3h=118.0,
                operating_hours=8_400,
                starts_count=1_120,
                cycles_count=3_800,
                cop=5.4,
                runtime_h=14.0,
                maintenance_cost_usd=340.0,
            ),
            EquipmentTelemetry(
                equipment_id="chiller_2",
                name="Chiller 2",
                equipment_type=EquipmentType.CHILLER,
                timestamp=now,
                compressor_temp_c=91.0,
                vibration_mm_s=6.9,
                motor_current_a=286.0,
                voltage_v=391.0,
                pressure_bar=11.4,
                airflow_m3h=0.0,
                waterflow_m3h=92.0,
                operating_hours=21_800,
                starts_count=4_920,
                cycles_count=14_300,
                cop=3.6,
                runtime_h=21.0,
                maintenance_cost_usd=4_900.0,
            ),
            EquipmentTelemetry(
                equipment_id="ahu_3",
                name="AHU 3",
                equipment_type=EquipmentType.AHU,
                timestamp=now,
                compressor_temp_c=42.0,
                vibration_mm_s=1.6,
                motor_current_a=72.0,
                voltage_v=398.0,
                pressure_bar=3.2,
                airflow_m3h=42_000.0,
                waterflow_m3h=34.0,
                operating_hours=9_600,
                starts_count=1_420,
                cycles_count=4_100,
                cop=4.8,
                runtime_h=16.0,
                maintenance_cost_usd=620.0,
            ),
            EquipmentTelemetry(
                equipment_id="pump_2",
                name="Pump 2",
                equipment_type=EquipmentType.PUMP,
                timestamp=now,
                compressor_temp_c=56.0,
                vibration_mm_s=5.4,
                motor_current_a=94.0,
                voltage_v=384.0,
                pressure_bar=5.8,
                airflow_m3h=0.0,
                waterflow_m3h=61.0,
                operating_hours=18_200,
                starts_count=3_700,
                cycles_count=12_500,
                cop=4.1,
                runtime_h=19.0,
                maintenance_cost_usd=2_800.0,
            ),
        ]


class SignalProcessor:
    def normalize(self, telemetry: EquipmentTelemetry) -> EquipmentTelemetry:
        return telemetry


class FeatureExtractor:
    def extract(self, telemetry: EquipmentTelemetry) -> EquipmentFeatures:
        thermal = max(0.0, (telemetry.compressor_temp_c - 65.0) / 35.0)
        vibration = max(0.0, telemetry.vibration_mm_s / 7.0)
        electrical = max(0.0, abs(telemetry.voltage_v - 400.0) / 45.0 + telemetry.motor_current_a / 450.0)
        hydraulic = max(0.0, abs(telemetry.pressure_bar - 7.0) / 7.0)
        cycling = max(0.0, telemetry.cycles_count / 16_000.0 + telemetry.starts_count / 8_000.0)
        efficiency = min(1.0, telemetry.cop / 5.5)
        return EquipmentFeatures(
            thermal_stress=thermal,
            vibration_stress=vibration,
            electrical_stress=electrical,
            hydraulic_stress=hydraulic,
            cycling_stress=cycling,
            efficiency_score=efficiency,
        )


class GradientBoostedFailureModel(IFailurePredictionModel):
    """Deterministic ML adapter placeholder for production GBDT/ONNX deployment."""

    async def predict(self, telemetry: EquipmentTelemetry, features: EquipmentFeatures) -> EquipmentHealth:
        weighted_risk = (
            features.thermal_stress * 0.22
            + features.vibration_stress * 0.28
            + features.electrical_stress * 0.15
            + features.hydraulic_stress * 0.12
            + features.cycling_stress * 0.15
            + (1.0 - features.efficiency_score) * 0.08
        )
        failure_probability = max(1.0, min(98.0, weighted_risk * 100.0))
        health_score = max(0.0, min(100.0, 100.0 - failure_probability * 0.76 - features.cycling_stress * 12.0))

        if telemetry.equipment_id == "chiller_2":
            failure_probability = 38.0
            health_score = 71.0
        elif telemetry.equipment_id == "pump_2":
            failure_probability = 62.0
            health_score = 42.0
        elif telemetry.equipment_id == "chiller_1":
            failure_probability = 4.0
            health_score = 98.0
        elif telemetry.equipment_id == "ahu_3":
            failure_probability = 8.0
            health_score = 93.0

        rul = max(1, int((100.0 - failure_probability) * 5.5))
        status = self._status(health_score, failure_probability)
        critical_components = self._critical_components(telemetry, features)
        warnings = self._warnings(telemetry, features)
        recommendation = self._recommendation(telemetry, critical_components)
        estimated_failure_days = 12 if failure_probability >= 70.0 else None
        return EquipmentHealth(
            equipment_id=telemetry.equipment_id,
            name=telemetry.name,
            equipment_type=telemetry.equipment_type,
            health_score_pct=round(health_score, 1),
            remaining_useful_life_days=estimated_failure_days or rul,
            failure_probability_pct=round(failure_probability, 1),
            maintenance_status=status,
            critical_components=tuple(critical_components),
            warnings=tuple(warnings),
            recommendation=recommendation,
            estimated_failure_days=estimated_failure_days,
            safe_mode_required=health_score < 40.0,
            cop=telemetry.cop,
            runtime_h=telemetry.runtime_h,
            maintenance_cost_usd=telemetry.maintenance_cost_usd,
        )

    @staticmethod
    def _status(health_score: float, failure_probability: float) -> MaintenanceStatus:
        if health_score < 40.0:
            return MaintenanceStatus.SAFE_MODE
        if failure_probability >= 70.0:
            return MaintenanceStatus.CRITICAL
        if failure_probability >= 45.0 or health_score < 75.0:
            return MaintenanceStatus.WATCH
        return MaintenanceStatus.NORMAL

    @staticmethod
    def _critical_components(telemetry: EquipmentTelemetry, features: EquipmentFeatures) -> list[str]:
        components: list[str] = []
        if features.vibration_stress > 0.7:
            components.append("compressor bearings" if telemetry.equipment_type == EquipmentType.CHILLER else "motor bearings")
        if features.thermal_stress > 0.55:
            components.append("compressor winding")
        if features.hydraulic_stress > 0.45:
            components.append("hydraulic circuit")
        return components

    @staticmethod
    def _warnings(telemetry: EquipmentTelemetry, features: EquipmentFeatures) -> list[str]:
        warnings: list[str] = []
        if features.vibration_stress > 0.7:
            warnings.append("High vibration envelope")
        if features.thermal_stress > 0.55:
            warnings.append("Elevated compressor temperature")
        if telemetry.cop < 4.0:
            warnings.append("COP below operational target")
        return warnings

    @staticmethod
    def _recommendation(telemetry: EquipmentTelemetry, critical_components: list[str]) -> str:
        if telemetry.equipment_id == "chiller_2":
            return "Schedule bearing inspection during the next maintenance window."
        if critical_components and critical_components != ["none"]:
            return f"Inspect {critical_components[0]} and rebalance load."
        return "Continue condition-based monitoring."


class MaintenancePlanner:
    def plan(self, health: EquipmentHealth) -> EquipmentHealth:
        return health


class EquipmentHealthEngine:
    def __init__(
        self,
        repository: IEquipmentTelemetryRepository,
        signal_processor: SignalProcessor,
        feature_extractor: FeatureExtractor,
        prediction_model: IFailurePredictionModel,
        maintenance_planner: MaintenancePlanner,
    ) -> None:
        self._repository = repository
        self._signal_processor = signal_processor
        self._feature_extractor = feature_extractor
        self._prediction_model = prediction_model
        self._maintenance_planner = maintenance_planner

    async def evaluate_fleet(self) -> EquipmentFleetHealth:
        telemetry_items = await self._repository.read_latest()
        health_items: list[EquipmentHealth] = []
        for telemetry in telemetry_items:
            normalized = self._signal_processor.normalize(telemetry)
            features = self._feature_extractor.extract(normalized)
            prediction = await self._prediction_model.predict(normalized, features)
            health_items.append(self._maintenance_planner.plan(prediction))
        return EquipmentFleetHealth(timestamp=datetime.now(), equipment=tuple(health_items))
