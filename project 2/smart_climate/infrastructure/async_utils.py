"""
Мост между синхронным исполнением Streamlit-скрипта и асинхронным ядром движка.

Streamlit выполняет скрипт синхронно на каждый rerun, поэтому весь
Location Intelligence Engine и Weather Data Fusion Engine написаны на AsyncIO
(для параллельных запросов к нескольким провайдерам), а наружу выставлена
одна синхронная функция `run_async`, которая корректно работает даже если
вокруг уже крутится собственный event loop (например, при встраивании
в Jupyter/ASGI-обвязку).
"""
from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Awaitable, TypeVar

_T = TypeVar("_T")


def run_async(coro: Awaitable[_T]) -> _T:
    """Выполнить корутину синхронно, независимо от наличия активного event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # Активного loop нет — обычный случай для Streamlit.
        return asyncio.run(coro)  # type: ignore[arg-type]

    # Loop уже работает в текущем потоке (редкий случай) — выполняем в отдельном потоке.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(asyncio.run, coro)  # type: ignore[arg-type]
        return future.result()
