"""Mall Analytics Engine."""

from .factory import build_mall_analytics_engine
from .models import MallAnalyticsReport

__all__ = ["MallAnalyticsReport", "build_mall_analytics_engine"]
