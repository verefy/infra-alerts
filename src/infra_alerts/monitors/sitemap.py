from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any
from xml.etree import ElementTree

from selectolax.parser import HTMLParser

from infra_alerts.fetcher import AsyncFetcher
from infra_alerts.models import ChangeEvent, CheckResult


def _parse_sitemap(xml_text: str) -> dict[str, str]:
    root = ElementTree.fromstring(xml_text)
    loc_to_lastmod: dict[str, str] = {}
    namespace = ""
    if root.tag.startswith("{") and "}" in root.tag:
        namespace = root.tag.split("}", maxsplit=1)[0] + "}"
    for url in root.findall(f"{namespace}url"):
        loc_node = url.find(f"{namespace}loc")
        if loc_node is None or loc_node.text is None:
            continue
        lastmod_node = url.find(f"{namespace}lastmod")
        loc = loc_node.text.strip()
        lastmod = lastmod_node.text.strip() if lastmod_node is not None and lastmod_node.text else ""
        if loc:
            loc_to_lastmod[loc] = lastmod
    return loc_to_lastmod


def _summarize_page(html: str) -> str:
    parser = HTMLParser(html)
    title = parser.css_first("title")
    heading = parser.css_first("h1")
    title_text = title.text(strip=True) if title is not None else ""
    heading_text = heading.text(strip=True) if heading is not None else ""
    if title_text and heading_text and title_text != heading_text:
        return f"{title_text} | {heading_text}"
    return title_text or heading_text or "(no title)"


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def check_sitemap(
    target: str,
    sitemap_url: str,
    previous_state: dict[str, Any],
    fetcher: AsyncFetcher,
    now: datetime,
) -> CheckResult:
    xml_text = await fetcher.get_text(sitemap_url)
    current_map = _parse_sitemap(xml_text)

    previous_map_raw = previous_state.get("page_lastmods", {})
    previous_map = previous_map_raw if isinstance(previous_map_raw, dict) else {}
    previous_hashes_raw = previous_state.get("page_hashes", {})
    previous_hashes = previous_hashes_raw if isinstance(previous_hashes_raw, dict) else {}

    if not previous_map:
        return CheckResult(
            target=target,
            events=[],
            state_update={
                "page_lastmods": current_map,
                "page_hashes": previous_hashes,
                "last_checked": now.isoformat(),
            },
        )

    changed_urls: list[str] = []
    for url, lastmod in current_map.items():
        if url not in previous_map or previous_map.get(url) != lastmod:
            changed_urls.append(url)

    events: list[ChangeEvent] = []
    updated_hashes = dict(previous_hashes)
    for url in changed_urls[:40]:
        try:
            page_html = await fetcher.get_text(url)
            summary = _summarize_page(page_html)
            content_hash = _hash_text(summary)
            if updated_hashes.get(url) == content_hash:
                continue
            updated_hashes[url] = content_hash
            events.append(
                ChangeEvent(
                    target=target,
                    summary=f"Updated page: {summary}",
                    link=url,
                    severity="info",
                    occurred_at=now,
                    kind="sitemap_change",
                )
            )
        except Exception:
            events.append(
                ChangeEvent(
                    target=target,
                    summary="Updated page detected but content fetch failed",
                    link=url,
                    severity="warning",
                    occurred_at=now,
                    kind="sitemap_change_fetch_failed",
                )
            )

    return CheckResult(
        target=target,
        events=events,
        state_update={
            "page_lastmods": current_map,
            "page_hashes": updated_hashes,
            "last_checked": now.isoformat(),
        },
    )
