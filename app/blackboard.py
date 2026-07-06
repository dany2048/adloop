"""
The Blackboard — shared substrate the agent society reads and writes.

A single Job holds the request, the Director's plan, the briefs/creatives in
flight, and an append-only `log` of every agent message. Agents post their
reasoning + handoffs to the log; that log is what the UI streams as
"watch the team work" and what the demo shows as visible negotiation.

Deliberately tiny and dependency-free: the intelligence lives in the agents,
this just coordinates them and records what happened.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class LogEntry:
    ts: float
    agent: str           # "director" | "strategist" | "copywriter" | "art_director" | "critic"
    kind: str            # "plan" | "assign" | "draft" | "render" | "verdict" | "revise" | "final" | "info"
    message: str         # human-readable line (shown in the stepper)
    data: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"ts": self.ts, "agent": self.agent, "kind": self.kind, "message": self.message, "data": self.data}


@dataclass
class Job:
    chat_request: str
    brand_kit_id: str | None = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: str = "pending"            # pending | running | done | error
    plan: dict[str, Any] = field(default_factory=dict)
    briefs: list[dict[str, Any]] = field(default_factory=list)
    creatives: list[dict[str, Any]] = field(default_factory=list)
    log: list[LogEntry] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "chat_request": self.chat_request,
            "brand_kit_id": self.brand_kit_id,
            "plan": self.plan,
            "briefs": self.briefs,
            "creatives": self.creatives,
            "log": [e.as_dict() for e in self.log],
        }


class Blackboard:
    """Wraps a Job, gives agents a uniform way to post to the shared log."""

    def __init__(self, job: Job, on_log: Callable[[LogEntry], None] | None = None):
        self.job = job
        self._on_log = on_log  # optional hook so a server can stream entries live (SSE)

    def post(self, agent: str, kind: str, message: str, **data: Any) -> LogEntry:
        entry = LogEntry(ts=time.time(), agent=agent, kind=kind, message=message, data=data)
        self.job.log.append(entry)
        if self._on_log:
            try:
                self._on_log(entry)
            except Exception:
                pass
        return entry

    # convenience accessors
    def set_status(self, status: str) -> None:
        self.job.status = status

    def set_plan(self, plan: dict[str, Any]) -> None:
        self.job.plan = plan

    def add_brief(self, brief: dict[str, Any]) -> None:
        self.job.briefs.append(brief)

    def add_creative(self, creative: dict[str, Any]) -> None:
        self.job.creatives.append(creative)
