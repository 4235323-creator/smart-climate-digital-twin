"""Dependency-injection composition root for Equipment Health Monitoring."""
from __future__ import annotations

from .engine import (
    DemoEquipmentTelemetryRepository,
    EquipmentHealthEngine,
    FeatureExtractor,
    GradientBoostedFailureModel,
    MaintenancePlanner,
    SignalProcessor,
)


def build_equipment_health_engine() -> EquipmentHealthEngine:
    return EquipmentHealthEngine(
        repository=DemoEquipmentTelemetryRepository(),
        signal_processor=SignalProcessor(),
        feature_extractor=FeatureExtractor(),
        prediction_model=GradientBoostedFailureModel(),
        maintenance_planner=MaintenancePlanner(),
    )
