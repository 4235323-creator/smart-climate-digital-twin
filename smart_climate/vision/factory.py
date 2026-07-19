"""Dependency-injection composition root for the Computer Vision Engine."""
from __future__ import annotations

from .engine import (
    ComputerVisionEngine,
    DemoIpCameraProvider,
    DeterministicPersonDetector,
    DeterministicTracker,
    ZoneOccupancyEstimator,
)


def build_computer_vision_engine() -> ComputerVisionEngine:
    zone_people = {
        "food_court": 125,
        "cinema": 43,
        "shops": 382,
        "parking": 94,
    }
    zone_camera_map = {
        "food_court": "ipcam-food-court-01",
        "cinema": "ipcam-cinema-01",
        "shops": "ipcam-shops-01",
        "parking": "ipcam-parking-01",
    }
    zone_catalog = {
        "food_court": ("Food Court", 780.0, 180),
        "cinema": ("Cinema", 620.0, 160),
        "shops": ("Shops", 3_600.0, 540),
        "parking": ("Parking", 5_500.0, 260),
    }
    return ComputerVisionEngine(
        camera_provider=DemoIpCameraProvider(zone_camera_map),
        detector=DeterministicPersonDetector(zone_people),
        tracker=DeterministicTracker(),
        estimator=ZoneOccupancyEstimator(zone_catalog),
    )
