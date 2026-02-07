from __future__ import annotations

from datetime import datetime
from typing import Any

from infra_alerts.fetcher import AsyncFetcher
from infra_alerts.models import ChangeEvent, CheckResult


def _parse_tweets(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ("tweets", "data", "results", "items"):
            if isinstance(payload.get(key), list):
                return [item for item in payload[key] if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _tweet_id(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    return None


def _tweet_url(account: str, item: dict[str, Any]) -> str:
    possible_url = item.get("url")
    if isinstance(possible_url, str) and possible_url:
        return possible_url
    tweet_id = item.get("id") or item.get("tweet_id") or item.get("id_str")
    return f"https://x.com/{account}/status/{tweet_id}"


async def check_account_tweets(
    target: str,
    account: str,
    previous_state: dict[str, Any],
    fetcher: AsyncFetcher,
    api_key: str,
    now: datetime,
) -> CheckResult:
    payload = await fetcher.get_json(
        "https://api.twitterapi.io/twitter/user/last_tweets",
        headers={"X-API-Key": api_key, "Accept": "application/json"},
        params={"userName": account, "count": "50"},
    )
    tweets = _parse_tweets(payload)
    tweets.sort(key=lambda item: _tweet_id(item.get("id") or item.get("tweet_id") or item.get("id_str")) or 0)

    previous_last = _tweet_id(previous_state.get("last_tweet_id"))
    current_last = previous_last
    new_events: list[ChangeEvent] = []

    for item in tweets:
        tweet_id = _tweet_id(item.get("id") or item.get("tweet_id") or item.get("id_str"))
        if tweet_id is None:
            continue
        if current_last is None or tweet_id > current_last:
            current_last = tweet_id
        if previous_last is None:
            continue
        if tweet_id <= previous_last:
            continue

        text = item.get("text") or item.get("full_text") or item.get("content") or "(no text)"
        new_events.append(
            ChangeEvent(
                target=target,
                summary=f"New tweet from @{account}: {str(text)[:220]}",
                link=_tweet_url(account, item),
                severity="info",
                occurred_at=now,
                kind="new_tweet",
                metadata={"account": account, "tweet_id": tweet_id},
            )
        )

    state_update: dict[str, Any] = {"last_checked": now.isoformat()}
    if current_last is not None:
        state_update["last_tweet_id"] = str(current_last)

    return CheckResult(target=target, events=new_events, state_update=state_update)
