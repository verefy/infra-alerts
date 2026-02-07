from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from importlib.metadata import PackageNotFoundError, version
from typing import Any
from zoneinfo import ZoneInfo

import structlog

from infra_alerts.alerting import EmailClient, SlackClient
from infra_alerts.config import Settings, get_settings
from infra_alerts.digest import build_daily_digest
from infra_alerts.fetcher import AsyncFetcher
from infra_alerts.models import AlertLevel, AlertPayload, ChangeEvent, PendingAlert
from infra_alerts.monitors import (
    check_account_tweets,
    check_changelog,
    check_github_docs,
    check_sitemap,
    check_status_page,
    fetch_monitor_statuses,
)
from infra_alerts.state import StateStore


def configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ]
    )


def utc_now() -> datetime:
    return datetime.now(UTC)


def parse_iso(value: str | None) -> datetime | None:
    if value is None or value == "":
        return None
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def should_run(last_checked: str | None, interval_minutes: int, now: datetime) -> bool:
    parsed = parse_iso(last_checked)
    if parsed is None:
        return True
    return (now - parsed) >= timedelta(minutes=interval_minutes)


def phase_to_level(phase: str) -> AlertLevel:
    if phase in {"major_outage", "partial_outage", "degraded"}:
        return "critical"
    if phase in {"maintenance", "monitoring"}:
        return "warning"
    if phase == "operational":
        return "resolved"
    return "info"


def is_backup_non_operational(phase: str) -> bool:
    return phase in {"major_outage", "partial_outage", "degraded", "maintenance"}


def is_primary_non_operational(state: str) -> bool:
    return state == "down"


def primary_monitor_id_for_target(settings: Settings, target_key: str) -> str | None:
    if target_key == "x_status":
        return settings.betterstack_x_monitor_id
    if target_key == "twitterapi_status":
        return settings.betterstack_twitterapi_monitor_id
    return None


def build_alert_id(source: str, summary: str, timestamp: datetime) -> str:
    raw = f"{source}|{summary}|{timestamp.replace(second=0, microsecond=0).isoformat()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def current_app_version() -> str:
    try:
        return version("infra-alerts")
    except PackageNotFoundError:
        return "unknown"


def normalize_version(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized if normalized else None


def version_transition_alert(
    previous_version: str | None,
    current_version: str,
    now: datetime,
    first_run: bool,
) -> AlertPayload | None:
    if first_run:
        return None
    if previous_version == current_version:
        return None
    previous_label = previous_version if previous_version is not None else "unknown"
    return AlertPayload(
        alert_id=build_alert_id("release", f"{previous_label}->{current_version}", now),
        source="release",
        level="info",
        title=f"🚀 Infra Alerts updated to v{current_version}",
        body=f"Version changed from v{previous_label} to v{current_version}.",
        links=[],
        created_at=now,
        tags=["release", "version"],
    )


def event_to_alert(event: ChangeEvent) -> AlertPayload:
    emoji_by_level = {
        "critical": "🔴",
        "warning": "⚠️",
        "info": "📝",
        "resolved": "🟢",
    }
    prefix = emoji_by_level[event.severity]
    title = f"{prefix} {event.target}"
    return AlertPayload(
        alert_id=build_alert_id(event.target, event.summary, event.occurred_at),
        source=event.target,
        level=event.severity,
        title=title,
        body=event.summary,
        links=[event.link] if event.link else [],
        created_at=event.occurred_at,
        tags=[event.kind],
    )


def group_tweet_alert(events: list[ChangeEvent], now: datetime, max_links: int) -> AlertPayload | None:
    if not events:
        return None
    sorted_events = sorted(events, key=lambda item: item.occurred_at)
    links = [event.link for event in sorted_events if event.link is not None]
    links = links[:max_links]
    accounts = sorted({str(event.metadata.get("account", "unknown")) for event in sorted_events})
    account_label = ", ".join("@" + account for account in accounts)
    body = (
        f"Detected {len(sorted_events)} new tweets in the last run across {account_label}."
        f" Showing up to {max_links} links."
    )
    return AlertPayload(
        alert_id=build_alert_id("tweets-grouped", str(len(sorted_events)), now),
        source="tweets",
        level="info",
        title="📢 New tweets detected",
        body=body,
        links=links,
        created_at=now,
        tags=["tweets"],
    )


def group_target_alert(target: str, events: list[ChangeEvent], now: datetime, max_links: int) -> AlertPayload:
    lines = [f"- {event.summary}" for event in events[:max_links]]
    links = [event.link for event in events if event.link is not None][:max_links]
    extra = len(events) - len(lines)
    if extra > 0:
        lines.append(f"- +{extra} more")
    body = "\n".join(lines)
    severity: AlertLevel = "warning" if any(event.severity == "warning" for event in events) else "info"
    if any(event.severity == "critical" for event in events):
        severity = "critical"
    return AlertPayload(
        alert_id=build_alert_id(f"{target}-summary", body, now),
        source=target,
        level=severity,
        title=f"📝 {target} updates",
        body=body,
        links=links,
        created_at=now,
        tags=["summary"],
    )


def next_retry_time(settings: Settings, now: datetime, attempts: int, first_failed_at: datetime) -> datetime | None:
    elapsed = now - first_failed_at
    if elapsed > timedelta(hours=settings.retry_max_hours):
        return None
    if attempts <= len(settings.retry_minutes):
        delay_minutes = settings.retry_minutes[attempts - 1]
    else:
        delay_minutes = settings.retry_tail_minutes
    return now + timedelta(minutes=delay_minutes)


def trim_sent_ids(ids: list[str], limit: int = 2000) -> list[str]:
    if len(ids) <= limit:
        return ids
    return ids[-limit:]


def record_change(state: dict[str, Any], event: ChangeEvent) -> None:
    digest = state.setdefault("digest", {})
    changes = digest.setdefault("changes", [])
    if isinstance(changes, list):
        changes.append(
            {
                "occurred_at": event.occurred_at.isoformat(),
                "target": event.target,
                "summary": event.summary,
                "severity": event.severity,
                "kind": event.kind,
            }
        )
        if len(changes) > 5000:
            del changes[:-5000]


def record_failed_check(state: dict[str, Any], target: str, error: str, now: datetime) -> None:
    digest = state.setdefault("digest", {})
    failed = digest.setdefault("failed_checks", [])
    if isinstance(failed, list):
        failed.append({"occurred_at": now.isoformat(), "target": target, "error": error})
        if len(failed) > 1000:
            del failed[:-1000]


async def deliver_alert(
    payload: AlertPayload,
    slack_client: SlackClient,
    email_client: EmailClient | None,
    log: structlog.stdlib.BoundLogger,
) -> bool:
    try:
        sent_to_slack = await slack_client.send(payload)
    except Exception as exc:
        log.exception("slack_send_failed", alert_id=payload.alert_id, error=str(exc))
        sent_to_slack = False

    if sent_to_slack:
        return True

    if email_client is None:
        return False

    try:
        sent_to_email = await email_client.send_alert(payload)
    except Exception as exc:
        log.exception("email_send_failed", alert_id=payload.alert_id, error=str(exc))
        return False
    return sent_to_email


async def run() -> int:
    configure_logging()
    log = structlog.get_logger().bind(service="infra-alerts")
    settings = get_settings()

    state_store = StateStore(settings.state_path, settings.pending_alerts_path)
    state = state_store.load_state()
    pending_raw = state_store.load_pending()

    now = utc_now()
    first_run = len(state.get("targets", {})) == 0

    targets: dict[str, Any] = state.setdefault("targets", {})
    digest = state.setdefault("digest", {})
    digest.setdefault("changes", [])
    digest.setdefault("alerts_sent", 0)
    digest.setdefault("failed_checks", [])
    digest.setdefault("last_sent_date", None)
    meta = state.setdefault("meta", {})
    sent_alert_ids = meta.setdefault("sent_alert_ids", [])
    if not isinstance(sent_alert_ids, list):
        sent_alert_ids = []
        meta["sent_alert_ids"] = sent_alert_ids

    watchdog_events: list[AlertPayload] = []
    last_successful_run = parse_iso(meta.get("last_successful_run"))
    watchdog_alerted = bool(meta.get("watchdog_alerted", False))
    if last_successful_run is not None:
        silent_for = now - last_successful_run
        if silent_for >= timedelta(minutes=settings.watchdog_max_silence_minutes) and not watchdog_alerted:
            watchdog_events.append(
                AlertPayload(
                    alert_id=build_alert_id("watchdog", "silent", now),
                    source="watchdog",
                    level="warning",
                    title="⚠️ Monitor watchdog",
                    body=f"No successful monitor run detected for {int(silent_for.total_seconds() // 60)} minutes.",
                    links=[],
                    created_at=now,
                    tags=["watchdog"],
                )
            )
            meta["watchdog_alerted"] = True
        if silent_for < timedelta(minutes=settings.watchdog_max_silence_minutes) and watchdog_alerted:
            watchdog_events.append(
                AlertPayload(
                    alert_id=build_alert_id("watchdog", "recovered", now),
                    source="watchdog",
                    level="resolved",
                    title="🟢 Monitor watchdog recovered",
                    body="Successful monitor runs resumed.",
                    links=[],
                    created_at=now,
                    tags=["watchdog"],
                )
            )
            meta["watchdog_alerted"] = False

    pending_models: list[PendingAlert] = []
    for pending_raw_item in pending_raw:
        try:
            pending_models.append(PendingAlert.model_validate(pending_raw_item))
        except Exception:
            log.warning("invalid_pending_alert_dropped", pending=pending_raw_item)

    new_alerts: list[AlertPayload] = []
    current_version = current_app_version()
    previous_version = normalize_version(meta.get("deployed_version"))
    version_alert = version_transition_alert(
        previous_version=previous_version,
        current_version=current_version,
        now=now,
        first_run=first_run,
    )
    if version_alert is not None:
        new_alerts.append(version_alert)
    meta["deployed_version"] = current_version

    def target_state(target_key: str) -> dict[str, Any]:
        current = targets.get(target_key)
        if isinstance(current, dict):
            return current
        value: dict[str, Any] = {}
        targets[target_key] = value
        return value

    async with AsyncFetcher(timeout_seconds=10.0, retries=3) as fetcher:
        primary_monitor_states: dict[str, str] = {}
        if settings.betterstack_enable_primary_gate:
            try:
                primary_monitor_states = await fetch_monitor_statuses(
                    fetcher=fetcher,
                    api_token=settings.betterstack_api_token or "",
                )
            except Exception as exc:
                record_failed_check(state, "betterstack_primary", str(exc), now)
                log.exception("betterstack_primary_fetch_failed", error=str(exc))

        status_checks = {
            "x_status": [settings.x_status_url, settings.x_incidents_url],
            "twitterapi_status": [settings.twitterapi_status_url],
        }

        for target_key, urls in status_checks.items():
            t_state = target_state(target_key)
            last_checked = t_state.get("last_checked")
            if not isinstance(last_checked, str):
                last_checked = None
            if not should_run(last_checked, settings.status_interval_minutes, now):
                continue
            try:
                result = await check_status_page(
                    target=target_key,
                    urls=urls,
                    previous_state=t_state,
                    fetcher=fetcher,
                    now=now,
                    alert_delay_minutes=0,
                )
                previous_failures = int(t_state.get("consecutive_failures", 0))
                if previous_failures >= settings.unreachable_alert_after_failures:
                    new_alerts.append(
                        AlertPayload(
                            alert_id=build_alert_id(target_key, "reachable_again", now),
                            source=target_key,
                            level="resolved",
                            title=f"🟢 {target_key} reachable again",
                            body=f"{target_key} recovered after {previous_failures} failed checks.",
                            links=urls[:1],
                            created_at=now,
                            tags=["recovery"],
                        )
                    )
                t_state.update(result.state_update)
                t_state["consecutive_failures"] = 0
                t_state["last_error"] = None
                for event in result.events:
                    record_change(state, event)

                monitor_id = primary_monitor_id_for_target(settings, target_key)
                primary_state = (
                    primary_monitor_states.get(monitor_id, "unknown")
                    if monitor_id is not None
                    else "unknown"
                )
                t_state["primary_state"] = primary_state

                current_phase_raw = result.state_update.get("phase")
                current_phase = current_phase_raw if isinstance(current_phase_raw, str) else "unknown"
                backup_alert_active = bool(t_state.get("backup_alert_active", False))
                silent_since_raw = t_state.get("primary_silent_since")
                silent_since = parse_iso(silent_since_raw if isinstance(silent_since_raw, str) else None)

                if is_backup_non_operational(current_phase):
                    if is_primary_non_operational(primary_state):
                        t_state["primary_silent_since"] = None
                    else:
                        if silent_since is None:
                            t_state["primary_silent_since"] = now.isoformat()
                            silent_since = now
                        silence_elapsed = now - silent_since
                        if (
                            silence_elapsed >= timedelta(minutes=settings.status_backup_alert_delay_minutes)
                            and not backup_alert_active
                        ):
                            phase_label = current_phase.replace("_", " ")
                            new_alerts.append(
                                AlertPayload(
                                    alert_id=build_alert_id(target_key, f"primary_silent_{phase_label}", now),
                                    source=target_key,
                                    level=phase_to_level(current_phase),
                                    title=f"⚠️ {target_key} backup incident",
                                    body=(
                                        f"Backup check detected {phase_label} while Better Stack stayed operational"
                                        f" for at least {settings.status_backup_alert_delay_minutes} minutes."
                                    ),
                                    links=urls[:1],
                                    created_at=now,
                                    tags=["backup_signal", "primary_silent"],
                                )
                            )
                            backup_alert_active = True
                        if backup_alert_active:
                            for event in result.events:
                                if event.kind != "status_update":
                                    continue
                                update_alert = event_to_alert(event)
                                update_alert.tags = update_alert.tags + ["backup_signal"]
                                new_alerts.append(update_alert)
                else:
                    t_state["primary_silent_since"] = None
                    if backup_alert_active:
                        new_alerts.append(
                            AlertPayload(
                                alert_id=build_alert_id(target_key, "backup_incident_resolved", now),
                                source=target_key,
                                level="resolved",
                                title=f"🟢 {target_key} backup incident resolved",
                                body="Backup-detected incident has recovered.",
                                links=urls[:1],
                                created_at=now,
                                tags=["backup_signal", "resolved"],
                            )
                        )
                        backup_alert_active = False
                t_state["backup_alert_active"] = backup_alert_active
            except Exception as exc:
                failures = int(t_state.get("consecutive_failures", 0)) + 1
                t_state["consecutive_failures"] = failures
                t_state["last_error"] = str(exc)
                t_state["last_checked"] = now.isoformat()
                record_failed_check(state, target_key, str(exc), now)
                if (
                    failures >= settings.unreachable_alert_after_failures
                    and not bool(t_state.get("unreachable_alerted", False))
                ):
                    new_alerts.append(
                        AlertPayload(
                            alert_id=build_alert_id(target_key, "unreachable", now),
                            source=target_key,
                            level="warning",
                            title=f"⚠️ {target_key} unreachable",
                            body=(
                                f"{target_key} has been unreachable for {failures} consecutive checks."
                                f" Last error: {str(exc)}"
                            ),
                            links=urls[:1],
                            created_at=now,
                            tags=["unreachable"],
                        )
                    )
                    t_state["unreachable_alerted"] = True
                continue
            t_state["unreachable_alerted"] = False

        tweet_events: list[ChangeEvent] = []
        tweet_accounts = {
            "api_tweets": settings.api_account_name,
            "xdevelopers_tweets": settings.xdevelopers_account_name,
        }
        for target_key, account in tweet_accounts.items():
            t_state = target_state(target_key)
            last_checked = t_state.get("last_checked")
            if not isinstance(last_checked, str):
                last_checked = None
            if not should_run(last_checked, settings.tweets_interval_minutes, now):
                continue
            try:
                result = await check_account_tweets(
                    target=target_key,
                    account=account,
                    previous_state=t_state,
                    fetcher=fetcher,
                    api_key=settings.twitterapi_io_key,
                    now=now,
                )
                t_state.update(result.state_update)
                t_state["consecutive_failures"] = 0
                t_state["last_error"] = None
                for event in result.events:
                    record_change(state, event)
                    tweet_events.append(event)
            except Exception as exc:
                failures = int(t_state.get("consecutive_failures", 0)) + 1
                t_state["consecutive_failures"] = failures
                t_state["last_error"] = str(exc)
                t_state["last_checked"] = now.isoformat()
                record_failed_check(state, target_key, str(exc), now)

        if tweet_events:
            grouped = group_tweet_alert(tweet_events, now, settings.max_links_per_alert)
            if grouped is not None:
                new_alerts.append(grouped)

        docs_targets = [
            "x_docs_github",
            "x_changelog",
            "twitterapi_changelog",
            "twitterapi_sitemap",
        ]

        for target_key in docs_targets:
            t_state = target_state(target_key)
            last_checked = t_state.get("last_checked")
            if not isinstance(last_checked, str):
                last_checked = None
            if not should_run(last_checked, settings.docs_interval_minutes, now):
                continue
            try:
                if target_key == "x_docs_github":
                    result = await check_github_docs(
                        target=target_key,
                        previous_state=t_state,
                        fetcher=fetcher,
                        repo=settings.github_docs_repo,
                        github_token=settings.github_token,
                        now=now,
                    )
                elif target_key == "x_changelog":
                    result = await check_changelog(
                        target=target_key,
                        url=settings.x_changelog_url,
                        previous_state=t_state,
                        fetcher=fetcher,
                        now=now,
                    )
                elif target_key == "twitterapi_changelog":
                    result = await check_changelog(
                        target=target_key,
                        url=settings.twitterapi_changelog_url,
                        previous_state=t_state,
                        fetcher=fetcher,
                        now=now,
                    )
                else:
                    result = await check_sitemap(
                        target=target_key,
                        sitemap_url=settings.twitterapi_sitemap_url,
                        previous_state=t_state,
                        fetcher=fetcher,
                        now=now,
                        include_patterns=settings.sitemap_include_patterns,
                        exclude_patterns=settings.sitemap_exclude_patterns,
                    )
                t_state.update(result.state_update)
                t_state["consecutive_failures"] = 0
                t_state["last_error"] = None
                if result.events:
                    for event in result.events:
                        record_change(state, event)
                    new_alerts.append(group_target_alert(target_key, result.events, now, settings.max_links_per_alert))
            except Exception as exc:
                failures = int(t_state.get("consecutive_failures", 0)) + 1
                t_state["consecutive_failures"] = failures
                t_state["last_error"] = str(exc)
                t_state["last_checked"] = now.isoformat()
                record_failed_check(state, target_key, str(exc), now)

    local_now = now.astimezone(ZoneInfo(settings.tz_name))
    last_digest_date = digest.get("last_sent_date")
    if (not isinstance(last_digest_date, str) or last_digest_date != local_now.date().isoformat()) and (
        local_now.hour >= settings.digest_hour_local
    ):
        new_alerts.append(build_daily_digest(state, now))
        digest["last_sent_date"] = local_now.date().isoformat()

    if first_run:
        new_alerts = [
            AlertPayload(
                alert_id=build_alert_id("init", "initialized", now),
                source="bootstrap",
                level="info",
                title="🚀 Verefy Infra Alerts initialized",
                body=f"Monitoring initialized for 8 targets across X and twitterapi.io. Version: v{current_version}.",
                links=[],
                created_at=now,
                tags=["bootstrap"],
            )
        ]

    all_alerts = watchdog_events + new_alerts

    slack_client = SlackClient(settings.slack_webhook_url)
    email_client = (
        EmailClient(settings.gmail_address or "", settings.gmail_app_password or "", settings.email_recipients)
        if settings.allow_email_fallback
        else None
    )

    remaining_pending: dict[str, PendingAlert] = {}

    for pending_item in pending_models:
        if pending_item.next_retry_at > now:
            remaining_pending[pending_item.payload.alert_id] = pending_item
            continue
        sent = await deliver_alert(pending_item.payload, slack_client, email_client, log)
        if sent:
            sent_alert_ids.append(pending_item.payload.alert_id)
            digest["alerts_sent"] = int(digest.get("alerts_sent", 0)) + 1
            continue
        attempts = pending_item.attempts + 1
        next_time = next_retry_time(settings, now, attempts, pending_item.first_failed_at)
        if next_time is None:
            log.error("alert_dropped_after_retry_window", alert_id=pending_item.payload.alert_id)
            continue
        remaining_pending[pending_item.payload.alert_id] = PendingAlert(
            payload=pending_item.payload,
            attempts=attempts,
            first_failed_at=pending_item.first_failed_at,
            next_retry_at=next_time,
        )

    sent_id_set = {str(value) for value in sent_alert_ids}
    for alert in all_alerts:
        if alert.alert_id in sent_id_set:
            continue
        if alert.alert_id in remaining_pending:
            continue
        sent = await deliver_alert(alert, slack_client, email_client, log)
        if sent:
            sent_alert_ids.append(alert.alert_id)
            sent_id_set.add(alert.alert_id)
            digest["alerts_sent"] = int(digest.get("alerts_sent", 0)) + 1
            continue
        next_time = next_retry_time(settings, now, 1, now)
        if next_time is None:
            continue
        remaining_pending[alert.alert_id] = PendingAlert(
            payload=alert,
            attempts=1,
            first_failed_at=now,
            next_retry_at=next_time,
        )

    meta["sent_alert_ids"] = trim_sent_ids([str(value) for value in sent_alert_ids])
    meta["last_successful_run"] = now.isoformat()

    state_store.save_state(state)
    state_store.save_pending([item.model_dump(mode="json") for item in remaining_pending.values()])

    return 0


async def _amain() -> int:
    return await run()


def main() -> int:
    return asyncio.run(_amain())


if __name__ == "__main__":
    raise SystemExit(main())
