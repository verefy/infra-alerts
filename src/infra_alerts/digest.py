from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from infra_alerts.models import AlertPayload


def _parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def build_daily_digest(state: dict[str, Any], now: datetime) -> AlertPayload:
    digest = state.get("digest", {})
    changes_raw = digest.get("changes", [])
    failed_raw = digest.get("failed_checks", [])

    changes = [item for item in changes_raw if isinstance(item, dict) and isinstance(item.get("occurred_at"), str)]
    failed = [item for item in failed_raw if isinstance(item, dict) and isinstance(item.get("occurred_at"), str)]

    cutoff = now - timedelta(hours=24)
    recent_changes = [item for item in changes if _parse_iso(str(item["occurred_at"])) >= cutoff]
    recent_failed = [item for item in failed if _parse_iso(str(item["occurred_at"])) >= cutoff]

    if not recent_changes and not recent_failed:
        body = "✅ All quiet — 0 changes detected across 8 targets in the last 24h"
    else:
        counter = Counter(item.get("target", "unknown") for item in recent_changes)
        lines = [f"{target}: {count}" for target, count in sorted(counter.items())]
        failed_targets = Counter(item.get("target", "unknown") for item in recent_failed)
        failed_lines = [f"{target}: {count}" for target, count in sorted(failed_targets.items())]

        body_parts = [
            "Last 24h summary:",
            f"- total changes: {len(recent_changes)}",
            f"- alerts sent: {int(digest.get('alerts_sent', 0))}",
        ]
        if lines:
            body_parts.append("- changes by target: " + ", ".join(lines))
        if failed_lines:
            body_parts.append("- failed checks: " + ", ".join(failed_lines))
        body = "\n".join(body_parts)

    return AlertPayload(
        alert_id=f"daily-digest-{now.date().isoformat()}",
        source="daily_digest",
        level="info",
        title="🧾 Daily infra digest",
        body=body,
        links=[],
        created_at=now,
        tags=["digest"],
    )
