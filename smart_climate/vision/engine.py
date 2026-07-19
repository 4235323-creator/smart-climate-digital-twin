"""Computer Vision Engine implementation.

The production boundary is intentionally interface-first: IP camera, detector,
tracker, and estimator can be replaced by real RTSP, YOLOv11/RT-DETR,
ByteTrack/DeepSORT, and edge inference adapters without changing MPC or UI.
"""
from __future__ import annotations

from datetime import datetime
from hashlib import sha1

from .models import (
    CameraFrame,
    HeatmapCell,
    ICameraProvider,
    ITracker,
    IVisionDetector,
    MovementDirection,
    OccupancyEstimator,
    OccupancyForecast,
    OccupancySnapshot,
    PersonDetection,
    PersonTrack,
    ZoneOccupancy,
)


class DemoIpCameraProvider(ICameraProvider):
    def __init__(self, zone_camera_map: dict[str, str]) -> None:
        self._zone_camera_map = zone_camera_map

    async def fetch_frames(self) -> list[CameraFrame]:
        now = datetime.now()
        return [
            CameraFrame(
                camera_id=camera_id,
                zone_id=zone_id,
                timestamp=now,
                width=1920,
                height=1080,
                payload_ref=f"rtsp://bms.local/{camera_id}/latest",
            )
            for zone_id, camera_id in self._zone_camera_map.items()
        ]


class DeterministicPersonDetector(IVisionDetector):
    """Industrial simulator for detector output with YOLOv11/RT-DETR semantics."""

    def __init__(self, zone_people: dict[str, int], detector_name: str = "YOLOv11 / RT-DETR") -> None:
        self.name = detector_name
        self._zone_people = zone_people

    async def detect_persons(self, frames: list[CameraFrame]) -> list[PersonDetection]:
        detections: list[PersonDetection] = []
        for frame in frames:
            people_count = self._zone_people.get(frame.zone_id, 0)
            for idx in range(people_count):
                col = idx % 40
                row = idx // 40
                x1 = 20.0 + col * 45.0
                y1 = 30.0 + row * 42.0
                detections.append(
                    PersonDetection(
                        detection_id=f"{frame.zone_id}-{idx}",
                        camera_id=frame.camera_id,
                        zone_id=frame.zone_id,
                        confidence=0.91,
                        bbox_xyxy=(x1, y1, x1 + 32.0, y1 + 76.0),
                    )
                )
        return detections


class DeterministicTracker(ITracker):
    """ByteTrack/DeepSORT-compatible tracker simulator."""

    def __init__(self, tracker_name: str = "ByteTrack / DeepSORT") -> None:
        self.name = tracker_name

    async def update_tracks(self, detections: list[PersonDetection]) -> list[PersonTrack]:
        tracks: list[PersonTrack] = []
        for detection in detections:
            x1, y1, x2, y2 = detection.bbox_xyxy
            digest = int(sha1(detection.detection_id.encode("utf-8")).hexdigest(), 16)
            direction = (
                MovementDirection.QUEUING
                if detection.zone_id in {"food_court", "cinema"} and digest % 5 == 0
                else MovementDirection.INBOUND
                if digest % 3 == 0
                else MovementDirection.CIRCULATING
            )
            tracks.append(
                PersonTrack(
                    track_id=f"trk-{detection.detection_id}",
                    camera_id=detection.camera_id,
                    zone_id=detection.zone_id,
                    centroid_xy=((x1 + x2) / 2.0, (y1 + y2) / 2.0),
                    dwell_time_sec=float(180 + digest % 2400),
                    speed_mps=float(0.2 + (digest % 130) / 100.0),
                    direction=direction,
                )
            )
        return tracks


class ZoneOccupancyEstimator(OccupancyEstimator):
    def __init__(self, zone_catalog: dict[str, tuple[str, float, int]]) -> None:
        self._zone_catalog = zone_catalog

    async def estimate(self, tracks: list[PersonTrack]) -> OccupancySnapshot:
        now = datetime.now()
        tracks_by_zone: dict[str, list[PersonTrack]] = {zone_id: [] for zone_id in self._zone_catalog}
        for track in tracks:
            tracks_by_zone.setdefault(track.zone_id, []).append(track)

        zones: list[ZoneOccupancy] = []
        for zone_id, (zone_name, area_m2, capacity) in self._zone_catalog.items():
            zone_tracks = tracks_by_zone.get(zone_id, [])
            people_count = len(zone_tracks)
            queue_length = sum(1 for track in zone_tracks if track.direction == MovementDirection.QUEUING)
            dwell = (
                sum(track.dwell_time_sec for track in zone_tracks) / max(1, people_count) / 60.0
            )
            inbound = sum(1 for track in zone_tracks if track.direction == MovementDirection.INBOUND) / 5.0
            outbound = max(0.0, inbound * 0.72 - queue_length * 0.03)
            direction = MovementDirection.QUEUING if queue_length > people_count * 0.08 else MovementDirection.CIRCULATING
            zones.append(
                ZoneOccupancy(
                    zone_id=zone_id,
                    zone_name=zone_name,
                    people_count=people_count,
                    area_m2=area_m2,
                    capacity_people=capacity,
                    queue_length=queue_length,
                    avg_dwell_time_min=round(dwell, 1),
                    inbound_flow_people_min=round(inbound, 1),
                    outbound_flow_people_min=round(outbound, 1),
                    movement_direction=direction,
                )
            )

        heatmap = self._build_heatmap(zones)
        forecast = self._build_forecast(zones)
        return OccupancySnapshot(
            timestamp=now,
            zones=tuple(zones),
            heatmap=tuple(heatmap),
            forecast=tuple(forecast),
            detector_name="YOLOv11 / RT-DETR",
            tracker_name="ByteTrack / DeepSORT",
            source_quality=0.96,
        )

    @staticmethod
    def _build_heatmap(zones: list[ZoneOccupancy]) -> list[HeatmapCell]:
        max_density = max((zone.density_people_m2 for zone in zones), default=1.0)
        cells: list[HeatmapCell] = []
        layout = {"food_court": (0, 0), "cinema": (1, 0), "shops": (0, 1), "parking": (1, 1)}
        for zone in zones:
            x0, y0 = layout.get(zone.zone_id, (0, 0))
            intensity = zone.density_people_m2 / max_density if max_density > 0 else 0.0
            for dx in range(2):
                for dy in range(2):
                    cells.append(HeatmapCell(zone_id=zone.zone_id, x=x0 * 2 + dx, y=y0 * 2 + dy, intensity=intensity))
        return cells

    @staticmethod
    def _build_forecast(zones: list[ZoneOccupancy]) -> list[OccupancyForecast]:
        growth = {15: 1.06, 30: 1.14, 60: 1.28}
        forecasts: list[OccupancyForecast] = []
        peak_zone = max(zones, key=lambda zone: zone.load_factor)
        total_people = sum(zone.people_count for zone in zones)
        for horizon, factor in growth.items():
            forecasts.append(
                OccupancyForecast(
                    horizon_min=horizon,
                    total_people=int(total_people * factor),
                    peak_zone_id=peak_zone.zone_id,
                    expected_load_factor=round(peak_zone.load_factor * factor, 2),
                )
            )
        return forecasts


class ComputerVisionEngine:
    def __init__(
        self,
        camera_provider: ICameraProvider,
        detector: IVisionDetector,
        tracker: ITracker,
        estimator: OccupancyEstimator,
    ) -> None:
        self._camera_provider = camera_provider
        self._detector = detector
        self._tracker = tracker
        self._estimator = estimator

    async def analyze_occupancy(self) -> OccupancySnapshot:
        frames = await self._camera_provider.fetch_frames()
        detections = await self._detector.detect_persons(frames)
        tracks = await self._tracker.update_tracks(detections)
        return await self._estimator.estimate(tracks)
