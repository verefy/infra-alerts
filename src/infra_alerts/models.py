from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

AlertLevel = Literal["critical", "warning", "info", "resolved"]


class ChangeEvent(BaseModel):
    target: str
    summary: str
    link: str | None = None
    severity: AlertLevel = "info"
    occurred_at: datetime
    kind: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class AlertPayload(BaseModel):
    alert_id: str
    source: str
    level: AlertLevel
    title: str
    body: str
    links: list[str] = Field(default_factory=list)
    created_at: datetime
    tags: list[str] = Field(default_factory=list)


class CheckResult(BaseModel):
    target: str
    events: list[ChangeEvent] = Field(default_factory=list)
    state_update: dict[str, Any] = Field(default_factory=dict)


class PendingAlert(BaseModel):
    payload: AlertPayload
    attempts: int
    first_failed_at: datetime
    next_retry_at: datetime
