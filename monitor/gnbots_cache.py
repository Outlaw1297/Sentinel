"""Short-lived cache for GnBots API fetches shared across dashboard, settings, and push."""

from __future__ import annotations

import time
from typing import Any, Callable

_GNBOTS_FETCH_CACHE: dict[str, Any] = {"at": 0.0, "data": None}
_BOT_ACTIVITY_CACHE: dict[str, Any] = {"at": 0.0, "data": None}
_API_STATUS_CACHE: dict[str, Any] = {"at": 0.0, "data": None}

DEFAULT_TTL_SECONDS = 8.0


def gnbots_cache_ttl(config: dict[str, Any]) -> float:
    raw = config.get("gnbots_fetch_cache_seconds")
    if raw is not None:
        return max(0.0, float(raw))
    return DEFAULT_TTL_SECONDS


def invalidate_gnbots_caches() -> None:
    _GNBOTS_FETCH_CACHE["at"] = 0.0
    _GNBOTS_FETCH_CACHE["data"] = None
    _BOT_ACTIVITY_CACHE["at"] = 0.0
    _BOT_ACTIVITY_CACHE["data"] = None
    _API_STATUS_CACHE["at"] = 0.0
    _API_STATUS_CACHE["data"] = None


def _cache_get(bucket: dict[str, Any], ttl: float) -> Any | None:
    if ttl <= 0:
        return None
    data = bucket.get("data")
    if data is None:
        return None
    if time.time() - float(bucket.get("at") or 0.0) >= ttl:
        return None
    return data


def _cache_set(bucket: dict[str, Any], data: Any) -> Any:
    bucket["at"] = time.time()
    bucket["data"] = data
    return data


def cached_gnbots_fetch(config: dict[str, Any], fetcher: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
    ttl = gnbots_cache_ttl(config)
    cached = _cache_get(_GNBOTS_FETCH_CACHE, ttl)
    if cached is not None:
        return cached
    return _cache_set(_GNBOTS_FETCH_CACHE, fetcher(config))


def cached_bot_activity(config: dict[str, Any], fetcher: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
    ttl = gnbots_cache_ttl(config)
    cached = _cache_get(_BOT_ACTIVITY_CACHE, ttl)
    if cached is not None:
        return cached
    return _cache_set(_BOT_ACTIVITY_CACHE, fetcher(config))


def cached_api_status(config: dict[str, Any], fetcher: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
    ttl = gnbots_cache_ttl(config)
    cached = _cache_get(_API_STATUS_CACHE, ttl)
    if cached is not None:
        return cached
    return _cache_set(_API_STATUS_CACHE, fetcher(config))
