"""Dashboard cache must not keep a pre-command snapshot after Start/Stop."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import (
    _DASHBOARD_CACHE,
    _store_dashboard_payload,
    app,
    config,
    effective_dashboard_cache_seconds,
    fetch_gnbots_with_retry,
    invalidate_dashboard_cache,
)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def cache_settings():
    keys = ("dashboard_cache_seconds", "dashboard_cache_active_seconds")
    saved = {key: config.get(key) for key in keys}
    present = {key: key in config for key in keys}
    yield
    for key in keys:
        if present[key]:
            config[key] = saved[key]
        else:
            config.pop(key, None)


def test_disabled_cache_does_not_force_a_positive_ttl(cache_settings) -> None:
    config["dashboard_cache_seconds"] = 0
    config["dashboard_cache_active_seconds"] = 0

    assert effective_dashboard_cache_seconds({"gnbotsOnline": False, "botActive": False}) == 0
    assert effective_dashboard_cache_seconds({"gnbotsOnline": True, "botActive": False}) == 0
    assert effective_dashboard_cache_seconds({"gnbotsOnline": True, "botActive": True}) == 0


def test_configured_offline_cache_still_bounds_failed_polls(cache_settings) -> None:
    config["dashboard_cache_seconds"] = 60
    assert effective_dashboard_cache_seconds({"gnbotsOnline": False, "botActive": False}) == 60


def test_store_drops_build_invalidated_while_in_flight(cache_settings) -> None:
    config["dashboard_cache_active_seconds"] = 30
    invalidate_dashboard_cache()
    started = int(_DASHBOARD_CACHE["epoch"])
    invalidate_dashboard_cache()

    _store_dashboard_payload({"gnbotsOnline": True, "botActive": True, "profile": "stale"}, started)

    assert _DASHBOARD_CACHE["data"] is None


def test_store_discards_failed_snapshot_when_cache_disabled(cache_settings) -> None:
    config["dashboard_cache_seconds"] = 0
    config["dashboard_cache_active_seconds"] = 30
    invalidate_dashboard_cache()
    epoch = int(_DASHBOARD_CACHE["epoch"])
    _DASHBOARD_CACHE["at"] = 1_000_000_000.0
    _DASHBOARD_CACHE["data"] = {"gnbotsOnline": True, "botActive": True, "profile": "old"}

    _store_dashboard_payload({"gnbotsOnline": False, "botActive": False, "profile": "failed"}, epoch)

    assert _DASHBOARD_CACHE["data"] is None


def test_fresh_retry_does_not_reuse_gnbots_fetch_cache(monkeypatch) -> None:
    monkeypatch.setattr("app._fetch_gnbots_sync_uncached", lambda _config: {"live": True})

    async def cached(_config):
        return {"live": False}

    monkeypatch.setattr("app.fetch_gnbots", cached)
    result = asyncio.run(fetch_gnbots_with_retry({}, attempts=1, fresh=True))
    assert result == {"live": True}


def test_dashboard_fresh_bypasses_cached_payload(client, cache_settings, monkeypatch) -> None:
    config["dashboard_cache_seconds"] = 60
    config["dashboard_cache_active_seconds"] = 30
    monkeypatch.setattr("app.write_profiles_manifest", lambda *_args, **_kwargs: None)
    calls = {"n": 0, "fresh": None}

    async def fetch(_config, *, attempts=1, fresh=False):
        calls["n"] += 1
        calls["fresh"] = fresh
        return {"status": {}, "settings": {}, "sessions": []}

    def build(_config, _gnbots, _error):
        return {"gnbotsOnline": True, "botActive": False, "profile": f"built-{calls['n']}"}

    monkeypatch.setattr("app.fetch_gnbots_with_retry", fetch)
    monkeypatch.setattr("app.build_dashboard_payload", build)
    invalidate_dashboard_cache()

    first = client.get("/api/dashboard")
    assert first.status_code == 200
    assert first.json()["profile"] == "built-1"
    assert calls["n"] == 1

    second = client.get("/api/dashboard")
    assert second.json()["profile"] == "built-1"
    assert calls["n"] == 1

    fresh = client.get("/api/dashboard?fresh=1")
    assert fresh.json()["profile"] == "built-2"
    assert calls["fresh"] is True
    assert calls["n"] == 2


def test_inflight_dashboard_build_is_not_cached_after_invalidation(client, cache_settings, monkeypatch) -> None:
    config["dashboard_cache_active_seconds"] = 30
    monkeypatch.setattr("app.write_profiles_manifest", lambda *_args, **_kwargs: None)

    async def fetch(_config, *, attempts=1, fresh=False):
        invalidate_dashboard_cache()
        return {"status": {}, "settings": {}, "sessions": []}

    def build(_config, _gnbots, _error):
        return {"gnbotsOnline": True, "botActive": True, "profile": "pre-command"}

    monkeypatch.setattr("app.fetch_gnbots_with_retry", fetch)
    monkeypatch.setattr("app.build_dashboard_payload", build)
    invalidate_dashboard_cache()

    response = client.get("/api/dashboard")

    assert response.status_code == 200
    assert response.json()["profile"] == "pre-command"
    assert _DASHBOARD_CACHE["data"] is None


def test_command_clears_snapshot_stored_during_gnbots_call(client, monkeypatch) -> None:
    async def call(_config, **_kwargs):
        _DASHBOARD_CACHE["at"] = 1_000_000_000.0
        _DASHBOARD_CACHE["data"] = {"gnbotsOnline": True, "botActive": True, "profile": "before"}
        return {"ok": True, "status": 200, "data": {}}

    monkeypatch.setattr("app.call_gnbots", call)

    response = client.post("/api/commands/start")

    assert response.status_code == 200
    assert _DASHBOARD_CACHE["data"] is None
