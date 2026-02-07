from __future__ import annotations

from datetime import UTC, datetime

from infra_alerts.run_monitor import normalize_version, version_transition_alert


def test_normalize_version() -> None:
    assert normalize_version(" 0.2.0 ") == "0.2.0"
    assert normalize_version("") is None
    assert normalize_version(None) is None


def test_version_transition_alert_when_changed() -> None:
    now = datetime.now(UTC)
    alert = version_transition_alert(
        previous_version="0.1.0",
        current_version="0.2.0",
        now=now,
        first_run=False,
    )
    assert alert is not None
    assert alert.title == "🚀 Infra Alerts updated to v0.2.0"
    assert "v0.1.0" in alert.body


def test_version_transition_alert_skips_first_run_and_same_version() -> None:
    now = datetime.now(UTC)
    first_run_alert = version_transition_alert(
        previous_version=None,
        current_version="0.2.0",
        now=now,
        first_run=True,
    )
    same_version_alert = version_transition_alert(
        previous_version="0.2.0",
        current_version="0.2.0",
        now=now,
        first_run=False,
    )
    assert first_run_alert is None
    assert same_version_alert is None
