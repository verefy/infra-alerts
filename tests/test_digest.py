from __future__ import annotations

from datetime import UTC, datetime, timedelta

from infra_alerts.digest import build_daily_digest


def test_digest_all_quiet() -> None:
    state = {
        "digest": {
            "changes": [],
            "alerts_sent": 0,
            "failed_checks": [],
            "last_sent_date": None,
        }
    }
    now = datetime.now(UTC)
    payload = build_daily_digest(state, now)
    assert "All quiet" in payload.body


def test_digest_counts_changes() -> None:
    now = datetime.now(UTC)
    recent = (now - timedelta(hours=1)).isoformat()
    state = {
        "digest": {
            "changes": [
                {"occurred_at": recent, "target": "x_status", "summary": "a", "severity": "critical", "kind": "x"},
                {"occurred_at": recent, "target": "x_status", "summary": "b", "severity": "critical", "kind": "x"},
                {
                    "occurred_at": recent,
                    "target": "twitterapi_status",
                    "summary": "c",
                    "severity": "warning",
                    "kind": "x",
                },
            ],
            "alerts_sent": 3,
            "failed_checks": [{"occurred_at": recent, "target": "x_status", "error": "timeout"}],
            "last_sent_date": None,
        }
    }
    payload = build_daily_digest(state, now)
    assert "total changes: 3" in payload.body
    assert "x_status: 2" in payload.body
