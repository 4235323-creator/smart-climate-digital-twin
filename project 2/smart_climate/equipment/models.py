"""Domain models for Equipment Health Monitoring."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class MaintenanceStatus(str, Enum):
    NORMAL = "normal"
    WATCH = "watch"
    PLANNED = "planned"
    CRITICAL = "critical"
    SAFE_MODE = "safe_mode"


class EquipmentType(str, Enum):
    CHILLER = "chiller"
    AHU = "ahu"
    PUMP = "pump"


class EquipmentTelemetry(BaseModel):
    model_config = ConfigDict(frozen=True)

    equipment_id: str
    name: str
    equipment_type: EquipmentType
    timestamp: datetime
    compressor_temp_c: float
    vibration_mm_s: float
    motor_current_a: float
    voltage_v: float
    pressure_bar: float
    airflow_m3h: float
    waterflow_m3h: float
    operating_hours: float = Field(ge=0.0)
    starts_count: int = Field(ge=0)
    cycles_count: int = Field(ge=0)
    cop: float = Field(gt=0.0)
    runtime_h: float = Field(ge=0.0)
    maintenance_cost_usd: float = Field(ge=0.0)


class EquipmentFeatures(BaseModel):
    model_config = ConfigDict(frozen=True)

    thermal_stress: float = Field(ge=0.0)
    vibration_stress: float = Field(ge=0.0)
    electrical_stress: float = Field(ge=0.0)
    hydraulic_stress: float = Field(ge=0.0)
    cycling_stress: float = Field(ge=0.0)
    efficiency_score: float = Field(ge=0.0, le=1.0)


class EquipmentHealth(BaseModel):
    model_config = ConfigDict(frozen=True)

    equipment_id: str
    name: str
    equipment_type: EquipmentType
    health_score_pct: float = Field(ge=0.0, le=100.0)
    remaining_useful_life_days: int = Field(ge=0)
    failure_probability_pct: float = Field(ge=0.0, le=100.0)
    maintenance_status: MaintenanceStatus
    critical_components: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    recommendation: str = ""
    estimated_failure_days: int | None = None
    safe_mode_required: bool = False
    cop: float = Field(gt=0.0)
    runtime_h: float = Field(ge=0.0)
    maintenance_cost_usd: float = Field(ge=0.0)


class EquipmentFleetHealth(BaseModel):
    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    equipment: tuple[EquipmentHealth, ...]

    @property
    def average_health_score(self) -> float:
        if not self.equipment:
            return 100.0
        return sum(item.health_score_pct for item in self.equipment) / len(self.equipment)

    @property
    def critical_assets(self) -> tuple[EquipmentHealth, ...]:
        return tuple(
            item
            for item in self.equipment
            if item.safe_mode_required or item.failure_probability_pct >= 70.0
        )

    def get(self, equipment_id: str) -> EquipmentHealth | None:
        return next((item for item in self.equipment if item.equipment_id == equipment_id), None)


class IEquipmentTelemetryRepository(Protocol):
    async def read_latest(self) -> list[EquipmentTelemetry]:
        """Read latest HVAC telemetry from BMS, historian, or edge gateway."""


class IFailurePredictionModel(Protocol):
    async def predict(self, telemetry: EquipmentTelemetry, features: EquipmentFeatures) -> EquipmentHealth:
        """Predict Health Score, failure probability, and Remaining Useful Life."""
