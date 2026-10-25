"""Push notifications for APK updates and LDPlayer restores."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import push_notifications as push


def test_notify_apk_update_single_instance(monkeypatch):
    monkeypatch.setattr(push, "push_enabled", lambda _cfg=None: True)
    calls: list[tuple[str, str, str]] = []

    def _capture(title, body, *, tag="gnbots", url="/"):
        calls.append((title, body, tag))
        return {"ok": True, "sent": 1}

    monkeypatch.setattr(push, "send_push_notification", _capture)
    monkeypatch.setattr(push, "build_monitor_snapshot", lambda _cfg: {})

    result = push.notify_apk_update_result(
        {
            "index": 6,
            "installedVersion": "1.32.21",
            "message": "Installed Whiteout Survival 1.32.21 on instance 6.",
        },
        config={"push_enabled": True},
    )

    assert result == {"ok": True, "sent": 1}
    assert len(calls) == 1
    title, body, tag = calls[0]
    assert "instance 6" in title
    assert "1.32.21" in body
    assert tag == "apk-update-6"


def test_notify_apk_update_single_instance_resource_pack_incomplete(monkeypatch):
    monkeypatch.setattr(push, "push_enabled", lambda _cfg=None: True)
    calls: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        push,
        "send_push_notification",
        lambda title, body, *, tag="gnbots", url="/": calls.append((title, body, tag)) or {"ok": True, "sent": 1},
    )
    monkeypatch.setattr(push, "build_monitor_snapshot", lambda _cfg: {})

    push.notify_apk_update_result(
        {
            "index": 2,
            "installedVersion": "1.32.21",
            "message": (
                "Installed Whiteout Survival 1.32.21 on instance 2. "
                "Optional resource pack did not verify 100% completion."
            ),
            "resourcePack": {"completed": False, "reason": "timeout"},
        },
        config={"push_enabled": True},
    )

    title, body, tag = calls[0]
    assert "APK installed" in title
    assert "failed" not in title.lower()
    assert "1.32.21" in body
    assert "did not verify" not in body
    assert tag == "apk-update-2"


def test_notify_apk_update_batch_skips_noop(monkeypatch):
    monkeypatch.setattr(push, "push_enabled", lambda _cfg=None: True)
    calls: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        push,
        "send_push_notification",
        lambda title, body, *, tag="gnbots", url="/": calls.append((title, body, tag)) or {"ok": True, "sent": 1},
    )
    monkeypatch.setattr(push, "build_monitor_snapshot", lambda _cfg: {})

    assert push.notify_apk_update_result(
        {"updated": 0, "failed": 0, "message": "No updates needed."},
        config={"push_enabled": True},
    ) is None
    assert calls == []


def test_notify_apk_update_batch_with_failures(monkeypatch):
    monkeypatch.setattr(push, "push_enabled", lambda _cfg=None: True)
    calls: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        push,
        "send_push_notification",
        lambda title, body, *, tag="gnbots", url="/": calls.append((title, body, tag)) or {"ok": True, "sent": 1},
    )
    monkeypatch.setattr(push, "build_monitor_snapshot", lambda _cfg: {})

    push.notify_apk_update_result(
        {
            "updated": 2,
            "failed": 1,
            "message": "Updated 2 instances; 1 failed.",
            "failures": [{"index": 3, "error": "timeout"}],
        },
        config={"push_enabled": True},
    )

    assert len(calls) == 1
    title, body, tag = calls[0]
    assert "installed" in title.lower()
    assert "failed" in title.lower()
    assert "#3" in body
    assert tag == "apk-update-batch"


def test_notify_apk_update_failed(monkeypatch):
    monkeypatch.setattr(push, "push_enabled", lambda _cfg=None: True)
    calls: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        push,
        "send_push_notification",
        lambda title, body, *, tag="gnbots", url="/": calls.append((title, body, tag)) or {"ok": True, "sent": 1},
    )
    monkeypatch.setattr(push, "build_monitor_snapshot", lambda _cfg: {})

    push.notify_apk_update_failed(4, "Android did not finish booting", config={"push_enabled": True})

    assert calls[0][0] == "APK update failed: instance 4"
    assert "booting" in calls[0][1]
    assert calls[0][2] == "apk-update-failed-4"


def test_notify_restore_job_completed(monkeypatch):
    monkeypatch.setattr(push, "push_enabled", lambda _cfg=None: True)
    calls: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        push,
        "send_push_notification",
        lambda title, body, *, tag="gnbots", url="/": calls.append((title, body, tag)) or {"ok": True, "sent": 1},
    )
    monkeypatch.setattr(push, "build_monitor_snapshot", lambda _cfg: {})

    push.notify_restore_job_finished(
        {
            "status": "completed",
            "instanceIndex": 2,
            "instanceName": "Pam",
            "message": "Restored backup.ldbk to instance 2 (Pam).",
            "startedAt": "2026-07-09T16:00:00+00:00",
            "finishedAt": "2026-07-09T16:05:30+00:00",
            "apkInfo": {"installedVersion": "1.32.21"},
        },
        config={"push_enabled": True},
    )

    title, body, tag = calls[0]
    assert "Restore complete" in title
    assert "Pam" in title
    assert "5m 30s" in body
    assert "1.32.21" in body
    assert tag == "restore-complete-2"


def test_notify_restore_job_failed(monkeypatch):
    monkeypatch.setattr(push, "push_enabled", lambda _cfg=None: True)
    calls: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        push,
        "send_push_notification",
        lambda title, body, *, tag="gnbots", url="/": calls.append((title, body, tag)) or {"ok": True, "sent": 1},
    )
    monkeypatch.setattr(push, "build_monitor_snapshot", lambda _cfg: {})

    push.notify_restore_job_finished(
        {
            "status": "failed",
            "instanceIndex": 1,
            "instanceName": "Archer",
            "message": "ldconsole restore failed with code 1",
            "startedAt": "2026-07-09T16:00:00+00:00",
            "finishedAt": "2026-07-09T16:01:00+00:00",
        },
        config={"push_enabled": True},
    )

    title, body, tag = calls[0]
    assert "Restore failed" in title
    assert "Archer" in title
    assert "code 1" in body
    assert tag == "restore-failed-1"


def test_notify_restore_push_helper_calls_module():
    from ldplayer_restore import _notify_restore_push

    job = {
        "status": "completed",
        "instanceIndex": 0,
        "instanceName": "Test",
        "message": "done",
        "startedAt": "2026-07-09T16:00:00+00:00",
        "finishedAt": "2026-07-09T16:00:45+00:00",
    }
    with patch("push_notifications.notify_restore_job_finished") as mocked:
        _notify_restore_push(job, {"push_enabled": True})
        mocked.assert_called_once_with(job, config={"push_enabled": True})


def test_push_disabled_skips_apk_notification(monkeypatch):
    monkeypatch.setattr(push, "push_enabled", lambda _cfg=None: False)
    with patch.object(push, "send_push_notification") as mocked:
        assert push.notify_apk_update_result({"index": 1}, config={"push_enabled": False}) is None
        mocked.assert_not_called()


def test_notify_apk_update_started_batch(monkeypatch):
    monkeypatch.setattr(push, "push_enabled", lambda _cfg=None: True)
    calls: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        push,
        "send_push_notification",
        lambda title, body, *, tag="gnbots", url="/": calls.append((title, body, tag)) or {"ok": True, "sent": 1},
    )
    monkeypatch.setattr(push, "build_monitor_snapshot", lambda _cfg: {})

    push.notify_apk_update_started(
        {"indexes": [1, 2, 3], "total": 3, "source": "gnbots"},
        config={"push_enabled": True},
    )

    title, body, tag = calls[0]
    assert title == "APK update started"
    assert "3 instance" in body
    assert "gnbots" in body
    assert tag == "apk-update-start"


def test_notify_restore_job_started(monkeypatch):
    monkeypatch.setattr(push, "push_enabled", lambda _cfg=None: True)
    calls: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        push,
        "send_push_notification",
        lambda title, body, *, tag="gnbots", url="/": calls.append((title, body, tag)) or {"ok": True, "sent": 1},
    )
    monkeypatch.setattr(push, "build_monitor_snapshot", lambda _cfg: {})

    push.notify_restore_job_started(
        {
            "instanceIndex": 5,
            "instanceName": "Pam",
            "backupFile": "Pam.ldbk",
        },
        config={"push_enabled": True},
    )

    title, body, tag = calls[0]
    assert "Restore started" in title
    assert "Pam" in title
    assert "Pam.ldbk" in body
    assert tag == "restore-start-5"


def test_notify_available_update_program(monkeypatch):
    monkeypatch.setattr(push, "push_enabled", lambda _cfg=None: True)
    calls: list[tuple[str, str, str, str]] = []
    monkeypatch.setattr(
        push,
        "send_push_notification",
        lambda title, body, *, tag="gnbots", url="/": calls.append((title, body, tag, url))
        or {"ok": True, "sent": 1},
    )
    monkeypatch.setattr(push, "build_monitor_snapshot", lambda _cfg: {})

    push.notify_available_update(
        kind="program",
        local_version="0.2.3",
        remote_version="0.2.4",
        detail="hang fix",
        config={"push_enabled": True},
    )

    title, body, tag, url = calls[0]
    assert "Sentinel update available" in title
    assert "0.2.3" in body and "0.2.4" in body
    assert tag == "program-available-0.2.4"
    assert "monitor" in url


def test_notify_available_update_apk(monkeypatch):
    monkeypatch.setattr(push, "push_enabled", lambda _cfg=None: True)
    calls: list[tuple[str, str, str, str]] = []
    monkeypatch.setattr(
        push,
        "send_push_notification",
        lambda title, body, *, tag="gnbots", url="/": calls.append((title, body, tag, url))
        or {"ok": True, "sent": 1},
    )
    monkeypatch.setattr(push, "build_monitor_snapshot", lambda _cfg: {})

    push.notify_available_update(
        kind="apk",
        local_version="1.32.20",
        remote_version="1.32.21",
        config={"push_enabled": True},
    )

    title, body, tag, url = calls[0]
    assert "Whiteout APK" in title
    assert "1.32.21" in body
    assert tag == "apk-available-1.32.21"
    assert "restore" in url
