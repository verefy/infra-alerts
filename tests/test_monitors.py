from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from infra_alerts.monitors.github_docs import check_github_docs
from infra_alerts.monitors.status import check_status_page
from infra_alerts.monitors.tweets import check_account_tweets


class FakeFetcher:
    def __init__(self, payloads: dict[str, Any]) -> None:
        self.payloads = payloads

    async def get_text(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> str:
        value = self.payloads.get(url)
        if not isinstance(value, str):
            raise RuntimeError("missing text payload")
        return value

    async def get_json(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> Any:
        key = url
        if params and "per_page" in params:
            key = f"{url}?per_page={params['per_page']}"
        value = self.payloads.get(key, self.payloads.get(url))
        if value is None:
            raise RuntimeError("missing json payload")
        return value


@pytest.mark.asyncio
async def test_status_change_detection() -> None:
    fetcher = FakeFetcher(
        {
            "https://example.com/status": "<html><body>Major Outage currently active</body></html>",
        }
    )
    now = datetime.now(UTC)
    previous_state = {"phase": "operational", "content_hash": "abc", "incident_alerted": False}

    result = await check_status_page(
        target="x_status",
        urls=["https://example.com/status"],
        previous_state=previous_state,
        fetcher=fetcher,
        now=now,
        alert_delay_minutes=0,
    )
    assert len(result.events) == 1
    assert result.events[0].severity == "critical"


@pytest.mark.asyncio
async def test_tweets_returns_only_new_items() -> None:
    fetcher = FakeFetcher(
        {
            "https://api.twitterapi.io/twitter/user/last_tweets": {
                "tweets": [
                    {"id": "100", "text": "old"},
                    {"id": "101", "text": "new tweet"},
                ]
            }
        }
    )
    now = datetime.now(UTC)
    previous_state = {"last_tweet_id": "100"}

    result = await check_account_tweets(
        target="api_tweets",
        account="API",
        previous_state=previous_state,
        fetcher=fetcher,
        api_key="x",
        now=now,
    )
    assert len(result.events) == 1
    assert "new tweet" in result.events[0].summary


@pytest.mark.asyncio
async def test_github_docs_detects_new_commits() -> None:
    fetcher = FakeFetcher(
        {
            "https://api.github.com/repos/xdevplatform/docs/commits?per_page=20": [
                {"sha": "newsha", "html_url": "https://github.com/commit/newsha"},
                {"sha": "oldsha", "html_url": "https://github.com/commit/oldsha"},
            ],
            "https://api.github.com/repos/xdevplatform/docs/commits/newsha": {
                "commit": {"message": "Update docs"},
                "files": [{"filename": "a.mdx"}],
            },
        }
    )
    now = datetime.now(UTC)
    previous_state = {"last_commit_sha": "oldsha"}

    result = await check_github_docs(
        target="x_docs_github",
        previous_state=previous_state,
        fetcher=fetcher,
        repo="xdevplatform/docs",
        github_token=None,
        now=now,
    )
    assert len(result.events) == 1
    assert "Update docs" in result.events[0].summary
