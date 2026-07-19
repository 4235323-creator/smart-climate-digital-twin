"""Domain models and interfaces for Computer Vision Occupancy Analytics."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class MovementDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    CIRCULATING = "circulating"
    QUEUING = "queuing"


class CameraFrame(BaseModel):
    model_config = ConfigDict(frozen=True)

    camera_id: str
    zone_id: str
    timestamp: datetime
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    payload_ref: str = Field(description="Frame URI, RTSP marker, or object-storage reference.")


class PersonDetection(BaseModel):
    model_config = ConfigDict(frozen=True)

    detection_id: str
    camera_id: str
    zone_id: str
    confidence: float = Field(ge=0.0, le=1.0)
    bbox_xyxy: tuple[float, float, float, float]


class PersonTrack(BaseModel):
    model_config = ConfigDict(frozen=True)

    track_id: str
    camera_id: str
    zone_id: str
    centroid_xy: tuple[float, float]
    dwell_time_sec: float = Field(ge=0.0)
    speed_mps: float = Field(ge=0.0)
    direction: MovementDirection


class ZoneOccupancy(BaseModel):
    model_config = ConfigDict(frozen=True)

    zone_id: str
    zone_name: str
    people_count: int = Field(ge=0)
    area_m2: float = Field(gt=0)
    capacity_people: int = Field(gt=0)
    queue_length: int = Field(ge=0)
    avg_dwell_time_min: float = Field(ge=0.0)
    inbound_flow_people_min: float = Field(ge=0.0)
    outbound_flow_people_min: float = Field(ge=0.0)
    movement_direction: MovementDirection

    @property
    def density_people_m2(self) -> float:
        return self.people_count / self.area_m2

    @property
    def load_factor(self) -> float:
        return min(1.5, self.people_count / self.capacity_people)

    @property
    def hvac_demand_factor(self) -> float:
        return 1.0 + min(0.6, self.load_factor * 0.35)


class OccupancyForecast(BaseModel):
    model_config = ConfigDict(frozen=True)

    horizon_min: int
    total_people: int = Field(ge=0)
    peak_zone_id: str
    expected_load_factor: float = Field(ge=0.0)


class HeatmapCell(BaseModel):
    model_config = ConfigDict(frozen=True)

    zone_id: str
    x: int
    y: int
    intensity: float = Field(ge=0.0, le=1.0)


class OccupancySnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    zones: tuple[ZoneOccupancy, ...]
    heatmap: tuple[HeatmapCell, ...]
    forecast: tuple[OccupancyForecast, ...]
    detector_name: str
    tracker_name: str
    source_quality: float = Field(ge=0.0, le=1.0)

    @property
    def total_people(self) -> int:
        return sum(zone.people_count for zone in self.zones)

    @property
    def weighted_density(self) -> float:
        total_area = sum(zone.area_m2 for zone in self.zones)
        return 0.0 if total_area <= 0 else self.total_people / total_area

    @property
    def max_load_factor(self) -> float:
        return max((zone.load_factor for zone in self.zones), default=0.0)


class ICameraProvider(Protocol):
    async def fetch_frames(self) -> list[CameraFrame]:
        """Read the latest frames from IP cameras."""


class IVisionDetector(Protocol):
    async def detect_persons(self, frames: list[CameraFrame]) -> list[PersonDetection]:
        """Run YOLOv11 or RT-DETR person detection."""


class ITracker(Protocol):
    async def update_tracks(self, detections: list[PersonDetection]) -> list[PersonTrack]:
        """Run ByteTrack or DeepSORT multi-object tracking."""


class OccupancyEstimator(Protocol):
    async def estimate(self, tracks: list[PersonTrack]) -> OccupancySnapshot:
        """Convert tracks into occupancy, flow, queue, dwell, and density metrics."""
