"""
Smart Cache для Location Intelligence Engine.

Если пользователь уже искал объект — повторное геокодирование не выполняется.
Кэш живёт в памяти процесса (быстрый путь) и опционально персистится на диск
в JSON, чтобы переживать перезапуск Streamlit-приложения.
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Optional

from ..domain.models import LocationResult


class SmartLocationCache:
    """Потокобезопасный (в рамках asyncio) TTL-кэш результатов геокодинга."""

    def __init__(self, ttl_seconds: int = 24 * 3600, persist_path: Optional[Path] = None) -> None:
        self._ttl_seconds = ttl_seconds
        self._store: dict[str, tuple[float, list[LocationResult]]] = {}
        self._lock = asyncio.Lock()
        self._persist_path = persist_path
        if self._persist_path is not None and self._persist_path.exists():
            self._load_from_disk()

    @staticmethod
    def normalize_key(raw_key: str) -> str:
        return " ".join(raw_key.strip().lower().split())

    async def get(self, key: str) -> Optional[list[LocationResult]]:
        async with self._lock:
            normalized = self.normalize_key(key)
            entry = self._store.get(normalized)
            if entry is None:
                return None
            stored_at, results = entry
            if time.time() - stored_at > self._ttl_seconds:
                del self._store[normalized]
                return None
            return results

    async def set(self, key: str, results: list[LocationResult]) -> None:
        async with self._lock:
            normalized = self.normalize_key(key)
            self._store[normalized] = (time.time(), results)
            self._save_to_disk()

    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()
            self._save_to_disk()

    def _save_to_disk(self) -> None:
        if self._persist_path is None:
            return
        try:
            serializable = {
                key: {"stored_at": stored_at, "results": [r.model_dump(mode="json") for r in results]}
                for key, (stored_at, results) in self._store.items()
            }
            self._persist_path.write_text(json.dumps(serializable, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass  # Кэш на диске — best effort, не критичен для работы движка.

    def _load_from_disk(self) -> None:
        try:
            raw = json.loads(self._persist_path.read_text(encoding="utf-8"))  # type: ignore[union-attr]
            for key, payload in raw.items():
                results = [LocationResult.model_validate(item) for item in payload["results"]]
                self._store[key] = (payload["stored_at"], results)
        except (OSError, json.JSONDecodeError, KeyError, ValueError):
            self._store = {}
