"""Dependency-injection composition root for Mall Analytics Engine."""
from __future__ import annotations

from .engine import MallAnalyticsEngine


def build_mall_analytics_engine() -> MallAnalyticsEngine:
    return MallAnalyticsEngine()
