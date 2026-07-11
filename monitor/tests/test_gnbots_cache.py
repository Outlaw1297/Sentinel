"""Tests for short-lived GnBots API fetch cache."""

from __future__ import annotations

import time

from gnbots_cache import (
    cached_api_status,
    cached_gnbots_fetch,
    gnbots_cache_ttl,
    invalidate_gnbots_caches,
)


def test_gnbots_fetch_cache_hit_and_invalidation() -> None:
    invalidate_gnbots_caches()
    calls = {"count": 0}

    def fetcher(config: dict) -> dict:
        calls["count"] += 1
        return {"status": {"State": "Running"}, "settings": {}, "sessions": []}

    config = {"gnbots_fetch_cache_seconds": 8}
    first = cached_gnbots_fetch(config, fetcher)
    second = cached_gnbots_fetch(config, fetcher)

    assert first == second
    assert calls["count"] == 1

    invalidate_gnbots_caches()
    third = cached_gnbots_fetch(config, fetcher)
    assert third == first
    assert calls["count"] == 2


def test_api_status_cache_respects_ttl() -> None:
    invalidate_gnbots_caches()
    calls = {"count": 0}

    def status_fetcher(config: dict) -> dict:
        calls["count"] += 1
        return {"healthy": calls["count"] == 1}

    config = {"gnbots_fetch_cache_seconds": 0.05}
    assert gnbots_cache_ttl(config) == 0.05
    assert cached_api_status(config, status_fetcher)["healthy"] is True
    assert cached_api_status(config, status_fetcher)["healthy"] is True
    assert calls["count"] == 1
    time.sleep(0.06)
    assert cached_api_status(config, status_fetcher)["healthy"] is False
    assert calls["count"] == 2
