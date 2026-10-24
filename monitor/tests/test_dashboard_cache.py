"""Dashboard cache epoch / Start-Stop stale-payload race."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as app_module


@pytest.fixture
def client():
    return TestClient(app_module.app)


@pytest.fixture(autouse=True)
def _reset_dashboard_cache():
    app_module._DASHBOARD_CACHE.update(at=0.0, data=None, epoch=0)
    yield
    app_module._DASHBOARD_CACHE.update(at=0.0, data=None, epoch=0)


def test_effective_dashboard_cache_seconds_always_positive():
    with patch.object(app_module, "config", {"dashboard_cache_seconds": 0, "dashboard_cache_active_seconds": 5}):
        assert app_module.effective_dashboard_cache_seconds({"botActive": True, "gnbotsOnline": True}) == 10.0
        assert app_module.effective_dashboard_cache_seconds({"botActive": False, "gnbotsOnline": False}) == 30.0
        assert app_module.effective_dashboard_cache_seconds({"botActive": False, "gnbotsOnline": True}) == 30.0


def test_store_dashboard_cache_rejects_stale_epoch():
    payload = {"botActive": False, "gnbotsOnline": True, "profile": "x"}
    with patch.object(app_module, "config", {"dashboard_cache_seconds": 60}):
        epoch = app_module.dashboard_cache_epoch()
        assert app_module.store_dashboard_cache(payload, epoch=epoch) is True
        assert app_module._DASHBOARD_CACHE["data"] is payload

        app_module.invalidate_dashboard_cache()
        assert app_module._DASHBOARD_CACHE["data"] is None
        assert app_module.store_dashboard_cache(payload, epoch=epoch) is False
        assert app_module._DASHBOARD_CACHE["data"] is None


def test_dashboard_fresh_bypasses_cached_payload(client):
    stale = {"botActive": False, "gnbotsOnline": True, "profile": "stale", "marker": "old"}
    fresh = {"botActive": True, "gnbotsOnline": True, "profile": "fresh", "marker": "new"}
    app_module._DASHBOARD_CACHE.update(at=app_module.time.time(), data=stale, epoch=1)

    with patch.object(app_module, "config", {"dashboard_cache_seconds": 60, "dashboard_cache_active_seconds": 30}):
        with patch.object(app_module, "write_profiles_manifest"):
            with patch.object(app_module, "fetch_gnbots_with_retry", new_callable=AsyncMock, return_value={}):
                with patch.object(app_module, "build_dashboard_payload", return_value=fresh):
                    cached = client.get("/api/dashboard")
                    assert cached.status_code == 200
                    assert cached.json()["marker"] == "old"

                    rebuilt = client.get("/api/dashboard?fresh=1")
                    assert rebuilt.status_code == 200
                    assert rebuilt.json()["marker"] == "new"


def test_in_flight_build_does_not_repopulate_after_invalidate():
    """Simulate Start/Stop invalidating while a dashboard build still holds an old epoch."""
    stale = {"botActive": False, "gnbotsOnline": True, "profile": "pre-start"}
    with patch.object(app_module, "config", {"dashboard_cache_seconds": 60}):
        build_epoch = app_module.dashboard_cache_epoch()
        app_module.invalidate_dashboard_cache()  # Start/Stop mid-build
        assert app_module.store_dashboard_cache(stale, epoch=build_epoch) is False
        assert app_module._dashboard_cache_hit() is None


def test_global_command_invalidates_after_call(client):
    payload = {"botActive": False, "gnbotsOnline": True, "profile": "cached"}
    with patch.object(app_module, "config", {"dashboard_cache_seconds": 60}):
        assert app_module.store_dashboard_cache(payload, epoch=app_module.dashboard_cache_epoch())

        with patch.object(app_module, "call_gnbots", new_callable=AsyncMock) as mocked:
            mocked.return_value = {"ok": True}

            def _assert_cleared_during_call(*_args, **_kwargs):
                assert app_module._DASHBOARD_CACHE["data"] is None
                # Recache pre-change payload the way an in-flight rebuild would.
                app_module.store_dashboard_cache(payload, epoch=app_module.dashboard_cache_epoch())
                assert app_module._DASHBOARD_CACHE["data"] is payload
                return {"ok": True}

            mocked.side_effect = _assert_cleared_during_call
            response = client.post("/api/commands/start")
            assert response.status_code == 200
            assert mocked.await_count == 1
            # Post-command invalidate must drop the mid-command recache.
            assert app_module._DASHBOARD_CACHE["data"] is None
            assert app_module._dashboard_cache_hit() is None
