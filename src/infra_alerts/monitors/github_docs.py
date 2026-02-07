from __future__ import annotations

from datetime import datetime
from typing import Any

from infra_alerts.fetcher import AsyncFetcher
from infra_alerts.models import ChangeEvent, CheckResult


def _headers(token: str | None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def check_github_docs(
    target: str,
    previous_state: dict[str, Any],
    fetcher: AsyncFetcher,
    repo: str,
    github_token: str | None,
    now: datetime,
) -> CheckResult:
    commits_endpoint = f"https://api.github.com/repos/{repo}/commits"
    commits_payload = await fetcher.get_json(
        commits_endpoint,
        headers=_headers(github_token),
        params={"per_page": "20"},
    )
    commits = commits_payload if isinstance(commits_payload, list) else []
    if not commits:
        return CheckResult(target=target, events=[], state_update={"last_checked": now.isoformat()})

    latest_sha = str(commits[0].get("sha", ""))
    previous_sha = str(previous_state.get("last_commit_sha", ""))
    if previous_sha == "":
        return CheckResult(
            target=target,
            events=[],
            state_update={"last_commit_sha": latest_sha, "last_checked": now.isoformat()},
        )

    new_commits: list[dict[str, Any]] = []
    for commit in commits:
        sha = str(commit.get("sha", ""))
        if sha == "" or sha == previous_sha:
            break
        new_commits.append(commit)

    events: list[ChangeEvent] = []
    for commit in reversed(new_commits):
        sha = str(commit.get("sha", ""))
        if sha == "":
            continue
        details = await fetcher.get_json(
            f"https://api.github.com/repos/{repo}/commits/{sha}",
            headers=_headers(github_token),
        )
        files_raw = details.get("files") if isinstance(details, dict) else None
        changed_files: list[str] = []
        if isinstance(files_raw, list):
            changed_files = [str(item.get("filename", "")) for item in files_raw if isinstance(item, dict)]
        message = ""
        if isinstance(details, dict):
            commit_data = details.get("commit")
            if isinstance(commit_data, dict):
                message_data = commit_data.get("message")
                if isinstance(message_data, str):
                    message = message_data.splitlines()[0]
        summary = f"Commit: {message}" if message else f"Commit: {sha[:12]}"
        if changed_files:
            summary = f"{summary} | files: {', '.join(changed_files[:3])}"
        html_url = str(commit.get("html_url", "")) or None
        events.append(
            ChangeEvent(
                target=target,
                summary=summary,
                link=html_url,
                severity="info",
                occurred_at=now,
                kind="github_commit",
                metadata={"sha": sha, "files": changed_files[:20]},
            )
        )

    return CheckResult(
        target=target,
        events=events,
        state_update={"last_commit_sha": latest_sha, "last_checked": now.isoformat()},
    )
