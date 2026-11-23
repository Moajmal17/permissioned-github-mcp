"""Append-only audit log: one JSON line per tool call. Never logs the token."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path


class AuditLog:
    def __init__(self, path: str | Path | None):
        self.path = Path(path) if path else None

    def record(self, tool: str, repo: str, args: dict, outcome: str, detail: str = "") -> None:
        if not self.path:
            return
        entry = {
            "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "tool": tool,
            "repo": repo,
            "args": args,
            "outcome": outcome,  # allowed | denied | dry_run | error
            "detail": detail,
        }
        with self.path.open("a") as f:
            f.write(json.dumps(entry) + "\n")
