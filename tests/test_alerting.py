from __future__ import annotations

from datetime import UTC, datetime

import pytest

from infra_alerts.models import AlertPayload
from infra_alerts.run_monitor import deliver_alert, next_retry_time


class FakeSlack:
    def __init__(self, succeed: bool) -> None:
        self.succeed = succeed

    async def send(self, payload: AlertPayload) -> bool:
        return self.succeed


class FakeEmail:
    def __init__(self) -> None:
        self.calls = 0

    async def send_alert(self, payload: AlertPayload) -> bool:
        self.calls += 1
        return True


class FakeLog:
    def exception(self, event: str, **kwargs: object) -> None:
        _ = event
        _ = kwargs


class FakeSettings:
    retry_max_hours = 48
    retry_minutes = [1, 5, 15, 60]
    retry_tail_minutes = 360


@pytest.mark.asyncio
async def test_slack_failure_triggers_email() -> None:
    alert = AlertPayload(
        alert_id="a1",
        source="test",
        level="warning",
        title="warning",
        body="body",
        links=[],
        created_at=datetime.now(UTC),
        tags=[],
    )
    slack = FakeSlack(succeed=False)
    email = FakeEmail()

    sent = await deliver_alert(alert, slack, email, FakeLog())
    assert sent is True
    assert email.calls == 1


def test_retry_schedule() -> None:
    now = datetime.now(UTC)
    next_at = next_retry_time(FakeSettings(), now, 1, now)
    assert next_at is not None
    assert int((next_at - now).total_seconds()) == 60
