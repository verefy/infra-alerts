from __future__ import annotations

from infra_alerts.fetcher import AsyncFetcher


def normalize_monitor_status(value: str) -> str:
    lowered = value.strip().lower()
    if lowered in {"up", "down", "validating", "paused", "pending", "maintenance"}:
        return lowered
    return "unknown"


async def fetch_monitor_statuses(fetcher: AsyncFetcher, api_token: str) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Accept": "application/json",
    }
    endpoint = "https://uptime.betterstack.com/api/v2/monitors"
    statuses: dict[str, str] = {}

    next_url: str | None = endpoint
    pages = 0
    while next_url is not None and pages < 10:
        payload = await fetcher.get_json(next_url, headers=headers)
        pages += 1

        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                identifier = str(item.get("id", "")).strip()
                attributes = item.get("attributes")
                if identifier == "" or not isinstance(attributes, dict):
                    continue
                monitor_status = attributes.get("status")
                if not isinstance(monitor_status, str):
                    continue
                statuses[identifier] = normalize_monitor_status(monitor_status)

        next_link: str | None = None
        pagination = payload.get("pagination") if isinstance(payload, dict) else None
        if isinstance(pagination, dict):
            raw_next = pagination.get("next")
            if isinstance(raw_next, str) and raw_next.strip():
                next_link = raw_next.strip()
        next_url = next_link

    return statuses
