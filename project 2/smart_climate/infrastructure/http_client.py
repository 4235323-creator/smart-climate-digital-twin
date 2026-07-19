"""Фабрика общего асинхронного HTTP-клиента для всех внешних интеграций."""
from __future__ import annotations

import httpx

DEFAULT_TIMEOUT = httpx.Timeout(connect=4.0, read=6.0, write=4.0, pool=4.0)
DEFAULT_USER_AGENT = "SmartClimateDigitalTwin/2.0 (Location Intelligence Engine)"


def build_http_client() -> httpx.AsyncClient:
    """
    Создаёт AsyncClient с промышленными дефолтами:
    ограниченные таймауты (чтобы недоступный провайдер не блокировал каскад),
    единый User-Agent (обязателен для Nominatim/OSM policy) и keep-alive пул соединений.
    """
    return httpx.AsyncClient(
        timeout=DEFAULT_TIMEOUT,
        headers={"User-Agent": DEFAULT_USER_AGENT},
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        follow_redirects=True,
    )
