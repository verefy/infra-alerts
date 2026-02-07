from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any

from selectolax.parser import HTMLParser

from infra_alerts.fetcher import AsyncFetcher
from infra_alerts.models import ChangeEvent, CheckResult

MONTH_RE = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
DATE_PATTERNS = [
    re.compile(rf"{MONTH_RE}\s+\d{{1,2}},\s+\d{{4}}", re.IGNORECASE),
    re.compile(r"\d{4}-\d{2}-\d{2}"),
    re.compile(r"\d{1,2}/\d{1,2}/\d{4}"),
]


def _line_id(line: str) -> str:
    return hashlib.sha256(line.encode("utf-8")).hexdigest()


def _extract_candidate_lines(html: str) -> list[str]:
    tree = HTMLParser(html)
    text = tree.body.text(separator="\n") if tree.body is not None else tree.text()
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    lines = [line for line in lines if line and len(line) >= 6]

    selected: list[str] = []
    for line in lines:
        if any(pattern.search(line) for pattern in DATE_PATTERNS):
            selected.append(line)
            continue
        if line.lower().startswith(("release", "update", "change", "changelog", "new ")):
            selected.append(line)
    if not selected:
        selected = lines[:40]
    return selected[:120]


async def check_changelog(
    target: str,
    url: str,
    previous_state: dict[str, Any],
    fetcher: AsyncFetcher,
    now: datetime,
) -> CheckResult:
    html = await fetcher.get_text(url)
    entries = _extract_candidate_lines(html)
    entry_ids = [_line_id(entry) for entry in entries]
    previous_ids_raw = previous_state.get("entry_ids", [])
    previous_ids = [str(item) for item in previous_ids_raw] if isinstance(previous_ids_raw, list) else []

    if not previous_ids:
        return CheckResult(
            target=target,
            events=[],
            state_update={"entry_ids": entry_ids[:200], "last_checked": now.isoformat()},
        )

    seen = set(previous_ids)
    new_entries = [entry for entry in entries if _line_id(entry) not in seen]

    events: list[ChangeEvent] = []
    for entry in new_entries[:20]:
        events.append(
            ChangeEvent(
                target=target,
                summary=entry,
                link=url,
                severity="info",
                occurred_at=now,
                kind="changelog_entry",
            )
        )

    return CheckResult(
        target=target,
        events=events,
        state_update={"entry_ids": entry_ids[:200], "last_checked": now.isoformat()},
    )
