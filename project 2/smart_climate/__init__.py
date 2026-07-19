"""Smart Climate Digital Twin — промышленная платформа управления HVAC.

Слои:
    domain          — доменные модели (LocationResult, FusedDataState, ...)
    location        — Location Intelligence Engine (геокодинг, кэш, резолвер)
    weather         — Weather Data Fusion Engine (каскад погодных провайдеров)
    control         — MPC-контроллер HVAC
    infrastructure  — сквозные технические утилиты (HTTP-клиент, asyncio bridge)
"""
