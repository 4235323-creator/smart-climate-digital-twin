"""Mall Analytics Engine: footfall, tenant reports, forecasts, and HVAC impact."""
from __future__ import annotations

from datetime import date

from ..control.mpc import MpcResult
from ..vision.models import OccupancySnapshot
from .models import (
    AiRecommendation,
    HourlyFootfall,
    HvacImpact,
    MallAnalyticsReport,
    PdfReportJob,
    ReportPeriod,
    TenantAnalytics,
    VisitorForecast,
    WeekdayFootfall,
    ZoneTrafficShare,
)


class MallAnalyticsEngine:
    async def build_daily_report(
        self,
        occupancy: OccupancySnapshot,
        mpc_result: MpcResult,
        report_date: date | None = None,
    ) -> MallAnalyticsReport:
        current_date = report_date or date(2026, 7, 5)
        zones = self._zone_shares()
        return MallAnalyticsReport(
            report_date=current_date,
            total_visitors=48_254,
            peak_time="17:42",
            peak_occupancy_people=6_341,
            average_dwell_time_min=96,
            average_load_pct=72.0,
            max_loaded_zone="Food Court",
            average_flow_people_hour=4_012,
            black_friday_today_visitors=74_000,
            regular_day_visitors=41_000,
            black_friday_growth_pct=80.0,
            zones=tuple(zones),
            hourly_footfall=tuple(self._hourly_footfall()),
            weekday_analytics=tuple(self._weekday_analytics()),
            tenant_reports=tuple(self._tenant_reports()),
            hvac_impact=tuple(self._hvac_impact(mpc_result)),
            visitor_forecast=tuple(self._visitor_forecast()),
            ai_recommendations=tuple(self._recommendations(occupancy, mpc_result)),
            pdf_jobs=tuple(self._pdf_jobs(current_date)),
        )

    @staticmethod
    def _zone_shares() -> list[ZoneTrafficShare]:
        return [
            ZoneTrafficShare(zone_name="Food Court", visitors=18_337, share_pct=38.0, dwell_time_min=48, heatmap_level=10),
            ZoneTrafficShare(zone_name="Cinema", visitors=11_581, share_pct=24.0, dwell_time_min=132, heatmap_level=4),
            ZoneTrafficShare(zone_name="Fashion", visitors=9_168, share_pct=19.0, dwell_time_min=37, heatmap_level=7),
            ZoneTrafficShare(zone_name="Kids Zone", visitors=5_308, share_pct=11.0, dwell_time_min=85, heatmap_level=5),
            ZoneTrafficShare(zone_name="Parking", visitors=3_860, share_pct=8.0, dwell_time_min=22, heatmap_level=3),
        ]

    @staticmethod
    def _hourly_footfall() -> list[HourlyFootfall]:
        values = {
            "08:00": 320,
            "09:00": 870,
            "10:00": 2_100,
            "11:00": 3_800,
            "12:00": 5_100,
            "13:00": 5_740,
            "14:00": 5_960,
            "15:00": 5_880,
            "16:00": 6_050,
            "17:00": 6_341,
            "18:00": 6_120,
            "19:00": 5_430,
            "20:00": 3_910,
            "21:00": 2_013,
            "22:00": 620,
        }
        return [HourlyFootfall(hour=hour, visitors=visitors) for hour, visitors in values.items()]

    @staticmethod
    def _weekday_analytics() -> list[WeekdayFootfall]:
        return [
            WeekdayFootfall(weekday="Понедельник", visitors=21_000),
            WeekdayFootfall(weekday="Вторник", visitors=23_000),
            WeekdayFootfall(weekday="Среда", visitors=27_500),
            WeekdayFootfall(weekday="Четверг", visitors=31_000),
            WeekdayFootfall(weekday="Пятница", visitors=42_000),
            WeekdayFootfall(weekday="Суббота", visitors=61_000),
            WeekdayFootfall(weekday="Воскресенье", visitors=58_000),
        ]

    @staticmethod
    def _tenant_reports() -> list[TenantAnalytics]:
        return [
            TenantAnalytics(zone_name="Fashion Zone", visitors=18_520, conversion_pct=34.0, average_dwell_time_min=42),
            TenantAnalytics(zone_name="Food Court", visitors=18_337, conversion_pct=61.0, average_dwell_time_min=48),
            TenantAnalytics(zone_name="Cinema", visitors=11_581, conversion_pct=46.0, average_dwell_time_min=132),
        ]

    @staticmethod
    def _hvac_impact(mpc_result: MpcResult) -> list[HvacImpact]:
        energy_per_visitor = max(0.01, mpc_result.hvac_electric_power_kw * 12.0 / 48_254)
        cost_per_visitor = max(0.001, mpc_result.cost_per_hour_usd * 12.0 / 48_254)
        return [
            HvacImpact(
                zone_name="Food Court",
                cooling_delta_pct=18.0,
                ventilation_delta_pct=25.0,
                energy_delta_pct=11.0,
                energy_per_visitor_kwh=round(energy_per_visitor, 3),
                cost_per_visitor_usd=round(cost_per_visitor, 4),
            )
        ]

    @staticmethod
    def _visitor_forecast() -> list[VisitorForecast]:
        return [
            VisitorForecast(horizon="Через час", visitors=4_200, recommendation="Увеличить вентиляцию, запустить охлаждение, открыть дополнительные AHU"),
            VisitorForecast(horizon="Завтра", visitors=52_300, recommendation="Подготовить дневной cooling pre-start"),
            VisitorForecast(horizon="Через неделю", visitors=57_000, recommendation="Усилить staffing и проверить фильтры AHU"),
            VisitorForecast(horizon="Следующая суббота", visitors=68_000, recommendation="Включить weekend peak HVAC profile"),
            VisitorForecast(horizon="Черная пятница", visitors=94_000, recommendation="Активировать high-density crowd control и extended ventilation"),
        ]

    @staticmethod
    def _recommendations(occupancy: OccupancySnapshot, mpc_result: MpcResult) -> list[AiRecommendation]:
        return [
            AiRecommendation(
                trigger=f"Через час ожидается 4200 человек; текущий CV count {occupancy.total_people}",
                action="Увеличить вентиляцию, запустить охлаждение, открыть дополнительные AHU",
                expected_effect=f"Стабилизировать CO₂ около {mpc_result.co2_ppm} ppm и снизить тепловой пик Food Court",
            ),
            AiRecommendation(
                trigger="Food Court имеет максимальную загрузенность",
                action="Поднять cooling setpoint capacity на +18% и ventilation airflow на +25%",
                expected_effect="Снизить локальный перегрев и очереди у посадочных зон",
            ),
        ]

    @staticmethod
    def _pdf_jobs(report_date: date) -> list[PdfReportJob]:
        stamp = report_date.isoformat()
        return [
            PdfReportJob(period=ReportPeriod.DAILY, title="Daily Mall Analytics Report", filename=f"mall_daily_{stamp}.pdf", status="scheduled"),
            PdfReportJob(period=ReportPeriod.WEEKLY, title="Weekly Mall Analytics Report", filename=f"mall_weekly_{stamp}.pdf", status="scheduled"),
            PdfReportJob(period=ReportPeriod.MONTHLY, title="Monthly Mall Analytics Report", filename=f"mall_monthly_{stamp}.pdf", status="scheduled"),
            PdfReportJob(period=ReportPeriod.YEARLY, title="Yearly Mall Analytics Report", filename=f"mall_yearly_{stamp}.pdf", status="scheduled"),
        ]
