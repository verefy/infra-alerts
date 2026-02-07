from __future__ import annotations

from pathlib import Path

from infra_alerts.state import StateStore


def test_state_read_write_cycle(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    pending_path = tmp_path / "pending.json"
    store = StateStore(str(state_path), str(pending_path))

    state = store.load_state()
    assert state["version"] == 1

    state["targets"]["x_status"] = {"phase": "operational"}
    store.save_state(state)

    loaded = store.load_state()
    assert loaded["targets"]["x_status"]["phase"] == "operational"


def test_pending_read_write_cycle(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    pending_path = tmp_path / "pending.json"
    store = StateStore(str(state_path), str(pending_path))

    payload = [{"id": "a"}, {"id": "b"}]
    store.save_pending(payload)

    loaded = store.load_pending()
    assert len(loaded) == 2
    assert loaded[1]["id"] == "b"
