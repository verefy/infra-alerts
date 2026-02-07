from __future__ import annotations

from typing import Any

import pytest

from infra_alerts.monitors.betterstack import fetch_monitor_statuses, normalize_monitor_status


class FakeFetcher:
    def __init__(self, payload: Any) -> None:
        self.payload = payload

    async def get_json(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> Any:
        _ = url
        _ = headers
        _ = params
        return self.payload


def test_normalize_monitor_status() -> None:
    assert normalize_monitor_status("up") == "up"
    assert normalize_monitor_status("down") == "down"
    assert normalize_monitor_status("maintenance") == "maintenance"
    assert normalize_monitor_status("SomethingElse") == "unknown"


@pytest.mark.asyncio
async def test_fetch_monitor_statuses() -> None:
    payload = {
        "data": [
            {"id": "111", "attributes": {"status": "up"}},
            {"id": "222", "attributes": {"status": "down"}},
        ],
        "pagination": {"next": None},
    }
    fetcher = FakeFetcher(payload)
    states = await fetch_monitor_statuses(fetcher=fetcher, api_token="token")
    assert states["111"] == "up"
    assert states["222"] == "down"
