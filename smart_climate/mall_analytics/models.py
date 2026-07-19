"""Domain models for Mall Analytics reports."""
from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ReportPeriod(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class ZoneTrafficShare(BaseModel):
    model_config = ConfigDict(frozen=True)

    zone_name: str
    visitors: int = Field(ge=0)
    share_pct: float = Field(ge=0.0, le=100.0)
    dwell_time_min: int = Field(ge=0)
    heatmap_level: int = Field(ge=0, le=10)

    @property
    def heatmap_bar(self) -> str:
        return "█" * self.heatmap_level


class HourlyFootfall(BaseModel):
    model_config = ConfigDict(frozen=True)

    hour: str
    visitors: int = Field(ge=0)


class WeekdayFootfall(BaseModel):
    model_config = ConfigDict(frozen=True)

    weekday: str
    visitors: int = Field(ge=0)


class TenantAnalytics(BaseModel):
    model_config = ConfigDict(frozen=True)

    zone_name: str
    visitors: int = Field(ge=0)
    conversion_pct: float = Field(ge=0.0, le=100.0)
    average_dwell_time_min: int = Field(ge=0)


class HvacImpact(BaseModel):
    model_config = ConfigDict(frozen=True)

    zone_name: str
    cooling_delta_pct: float
    ventilation_delta_pct: float
    energy_delta_pct: float
    energy_per_visitor_kwh: float = Field(ge=0.0)
    cost_per_visitor_usd: float = Field(ge=0.0)


class VisitorForecast(BaseModel):
    model_config = ConfigDict(frozen=True)

    horizon: str
    visitors: int = Field(ge=0)
    recommendation: str


class AiRecommendation(BaseModel):
    model_config = ConfigDict(frozen=True)

    trigger: str
    action: str
    expected_effect: str


class PdfReportJob(BaseModel):
    model_config = ConfigDict(frozen=True)

    period: ReportPeriod
    title: str
    filename: str
    status: str


class MallAnalyticsReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    report_date: date
    total_visitors: int = Field(ge=0)
    peak_time: str
    peak_occupancy_people: int = Field(ge=0)
    average_dwell_time_min: int = Field(ge=0)
    average_load_pct: float = Field(ge=0.0, le=100.0)
    max_loaded_zone: str
    average_flow_people_hour: int = Field(ge=0)
    black_friday_today_visitors: int = Field(ge=0)
    regular_day_visitors: int = Field(ge=0)
    black_friday_growth_pct: float
    zones: tuple[ZoneTrafficShare, ...]
    hourly_footfall: tuple[HourlyFootfall, ...]
    weekday_analytics: tuple[WeekdayFootfall, ...]
    tenant_reports: tuple[TenantAnalytics, ...]
    hvac_impact: tuple[HvacImpact, ...]
    visitor_forecast: tuple[VisitorForecast, ...]
    ai_recommendations: tuple[AiRecommendation, ...]
    pdf_jobs: tuple[PdfReportJob, ...]

    @property
    def average_dwell_time_label(self) -> str:
        hours, minutes = divmod(self.average_dwell_time_min, 60)
        return f"{hours} час {minutes} минут" if hours else f"{minutes} минут"
