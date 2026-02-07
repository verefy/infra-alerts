from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def default_state() -> dict[str, Any]:
    return {
        "version": 1,
        "last_updated": now_iso(),
        "targets": {},
        "digest": {
            "changes": [],
            "alerts_sent": 0,
            "failed_checks": [],
            "last_sent_date": None,
        },
        "meta": {
            "last_successful_run": None,
            "watchdog_alerted": False,
            "sent_alert_ids": [],
            "deployed_version": None,
        },
    }


class StateStore:
    def __init__(self, state_path: str, pending_path: str) -> None:
        self.state_file = Path(state_path)
        self.pending_file = Path(pending_path)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.pending_file.parent.mkdir(parents=True, exist_ok=True)

    def load_state(self) -> dict[str, Any]:
        if not self.state_file.exists():
            return default_state()
        raw = self.state_file.read_text(encoding="utf-8").strip()
        if not raw:
            return default_state()
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return default_state()
        state = default_state()
        state.update(parsed)
        if not isinstance(state.get("targets"), dict):
            state["targets"] = {}
        if not isinstance(state.get("digest"), dict):
            state["digest"] = default_state()["digest"]
        if not isinstance(state.get("meta"), dict):
            state["meta"] = default_state()["meta"]
        return state

    def save_state(self, state: dict[str, Any]) -> None:
        state["last_updated"] = now_iso()
        self._atomic_dump(self.state_file, state)

    def load_pending(self) -> list[dict[str, Any]]:
        if not self.pending_file.exists():
            return []
        raw = self.pending_file.read_text(encoding="utf-8").strip()
        if not raw:
            return []
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            return []
        return [item for item in parsed if isinstance(item, dict)]

    def save_pending(self, pending: list[dict[str, Any]]) -> None:
        self._atomic_dump(self.pending_file, pending)

    def _atomic_dump(self, path: Path, payload: dict[str, Any] | list[dict[str, Any]]) -> None:
        with tempfile.NamedTemporaryFile("w", delete=False, dir=path.parent, encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
            handle.write("\n")
            tmp_path = Path(handle.name)
        tmp_path.replace(path)
