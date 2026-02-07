from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import Any

from selectolax.parser import HTMLParser

from infra_alerts.fetcher import AsyncFetcher
from infra_alerts.models import AlertLevel, ChangeEvent, CheckResult


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _extract_text(html: str) -> str:
    tree = HTMLParser(html)
    node = tree.body
    if node is None:
        return _normalize_space(tree.text())
    return _normalize_space(node.text(separator="\n"))


def _phase_from_text(text: str) -> str:
    lowered = text.lower()
    if "all systems operational" in lowered or "active incidents 0" in lowered:
        return "operational"
    if "major outage" in lowered:
        return "major_outage"
    if "partial outage" in lowered:
        return "partial_outage"
    if "degraded" in lowered:
        return "degraded"
    if "maintenance" in lowered:
        return "maintenance"
    if "monitoring" in lowered or "incident" in lowered:
        return "monitoring"
    if "operational" in lowered:
        return "operational"
    return "unknown"


def _level_for_phase(phase: str) -> AlertLevel:
    if phase in {"major_outage", "partial_outage", "degraded"}:
        return "critical"
    if phase in {"maintenance", "monitoring"}:
        return "warning"
    if phase == "operational":
        return "resolved"
    return "info"


def _hash_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _parse_iso(value: str | None) -> datetime | None:
    if value is None or value == "":
        return None
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


async def check_status_page(
    target: str,
    urls: list[str],
    previous_state: dict[str, Any],
    fetcher: AsyncFetcher,
    now: datetime,
    alert_delay_minutes: int,
) -> CheckResult:
    contents: list[str] = []
    for url in urls:
        html = await fetcher.get_text(url)
        contents.append(_extract_text(html))
    merged_text = "\n".join(contents)
    content_hash = _hash_text(merged_text)
    phase = _phase_from_text(merged_text)

    prev_phase = str(previous_state.get("phase", "unknown"))
    prev_hash = str(previous_state.get("content_hash", ""))
    incident_alerted = bool(previous_state.get("incident_alerted", False))
    pending_since = _parse_iso(previous_state.get("pending_incident_since"))

    events: list[ChangeEvent] = []
    state_update: dict[str, Any] = {
        "content_hash": content_hash,
        "phase": phase,
        "last_checked": now.isoformat(),
    }

    phase_non_operational = phase not in {"operational", "unknown"}
    prev_non_operational = prev_phase not in {"operational", "unknown"}

    if phase_non_operational:
        since = pending_since if pending_since is not None else now
        minutes_open = (now - since).total_seconds() / 60.0
        state_update["pending_incident_since"] = since.isoformat()

        if incident_alerted:
            if phase != prev_phase or content_hash != prev_hash:
                events.append(
                    ChangeEvent(
                        target=target,
                        summary=f"Status update: {phase.replace('_', ' ')}",
                        link=urls[0] if urls else None,
                        severity=_level_for_phase(phase),
                        occurred_at=now,
                        kind="status_update",
                    )
                )
        elif minutes_open >= float(alert_delay_minutes):
            events.append(
                ChangeEvent(
                    target=target,
                    summary=f"Incident detected: {phase.replace('_', ' ')}",
                    link=urls[0] if urls else None,
                    severity=_level_for_phase(phase),
                    occurred_at=now,
                    kind="incident_started",
                )
            )
            state_update["incident_alerted"] = True
        else:
            state_update["incident_alerted"] = False
    else:
        state_update["pending_incident_since"] = None
        state_update["incident_alerted"] = False
        if incident_alerted or prev_non_operational:
            events.append(
                ChangeEvent(
                    target=target,
                    summary="Service recovered and is operational",
                    link=urls[0] if urls else None,
                    severity="resolved",
                    occurred_at=now,
                    kind="incident_resolved",
                )
            )

    return CheckResult(target=target, events=events, state_update=state_update)
