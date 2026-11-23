"""Per-repo, per-tool permissions.

Every tool declares the scope it needs. A call runs only if the policy grants
that scope for the repo. Anything not listed falls back to the default, which
should be read-only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# Scopes are ordered: triage includes read, write includes triage and read.
SCOPE_ORDER = ["read", "triage", "write"]

TOOL_SCOPES = {
    "list_issues": "read",
    "get_issue": "read",
    "add_labels": "triage",
    "close_issue": "triage",
    "comment_on_issue": "write",
}


class PermissionDenied(Exception):
    pass


@dataclass
class Policy:
    repos: dict[str, str] = field(default_factory=dict)  # "owner/repo" -> highest scope
    default_scope: str | None = "read"
    dry_run_writes: bool = True

    @classmethod
    def load(cls, path: str | Path | None) -> "Policy":
        if not path:
            return cls()
        data = json.loads(Path(path).read_text())
        repos = {k.lower(): v["scope"] for k, v in data.get("repos", {}).items()}
        for scope in list(repos.values()) + [data.get("default_scope")]:
            if scope is not None and scope not in SCOPE_ORDER:
                raise ValueError(f"Unknown scope in policy: {scope!r}")
        return cls(
            repos=repos,
            default_scope=data.get("default_scope", "read"),
            dry_run_writes=data.get("dry_run_writes", True),
        )

    def granted_scope(self, repo: str) -> str | None:
        return self.repos.get(repo.lower(), self.default_scope)

    def check(self, tool: str, repo: str) -> None:
        needed = TOOL_SCOPES[tool]
        granted = self.granted_scope(repo)
        if granted is None or SCOPE_ORDER.index(granted) < SCOPE_ORDER.index(needed):
            raise PermissionDenied(
                f"'{tool}' needs '{needed}' on {repo}, but the policy grants "
                f"'{granted or 'nothing'}'. Edit the policy file to allow it."
            )

    def is_write(self, tool: str) -> bool:
        return TOOL_SCOPES[tool] != "read"
