"""MCP server: GitHub issue triage where every tool is a permission."""

from __future__ import annotations

import os
from typing import Any, Callable

from mcp.server.mcpserver import MCPServer

from .audit import AuditLog
from .github import GitHub, GitHubError
from .policy import PermissionDenied, Policy


class Gate:
    """Runs a tool only after the policy check, honours dry run, logs every call."""

    def __init__(self, policy: Policy, github: GitHub | None, audit: AuditLog):
        self.policy, self.github, self.audit = policy, github, audit

    def run(self, tool: str, repo: str, args: dict, call: Callable[[GitHub], Any]) -> Any:
        try:
            self.policy.check(tool, repo)
        except PermissionDenied as e:
            self.audit.record(tool, repo, args, "denied", str(e))
            return {"error": str(e)}
        if self.policy.is_write(tool) and self.policy.dry_run_writes:
            self.audit.record(tool, repo, args, "dry_run")
            return {"dry_run": True, "would_do": {"tool": tool, "repo": repo, **args},
                    "note": "Set dry_run_writes to false in the policy to make real changes."}
        if self.github is None:
            return {"error": "GITHUB_TOKEN is not set."}
        try:
            result = call(self.github)
        except GitHubError as e:
            self.audit.record(tool, repo, args, "error", str(e))
            return {"error": str(e)}
        self.audit.record(tool, repo, args, "allowed")
        return result


def build_server(gate: Gate) -> MCPServer:
    mcp = MCPServer("permissioned-github")

    @mcp.tool()
    def list_issues(repo: str, state: str = "open", limit: int = 20) -> Any:
        """List issues in a repo ("owner/name"). Needs: read."""
        return gate.run("list_issues", repo, {"state": state, "limit": limit},
                        lambda gh: gh.list_issues(repo, state, limit))

    @mcp.tool()
    def get_issue(repo: str, number: int) -> Any:
        """Get one issue, body truncated to keep context small. Needs: read."""
        return gate.run("get_issue", repo, {"number": number},
                        lambda gh: gh.get_issue(repo, number))

    @mcp.tool()
    def add_labels(repo: str, number: int, labels: list[str]) -> Any:
        """Add labels to an issue. Needs: triage."""
        return gate.run("add_labels", repo, {"number": number, "labels": labels},
                        lambda gh: gh.add_labels(repo, number, labels))

    @mcp.tool()
    def close_issue(repo: str, number: int) -> Any:
        """Close an issue. Needs: triage."""
        return gate.run("close_issue", repo, {"number": number},
                        lambda gh: gh.close_issue(repo, number))

    @mcp.tool()
    def comment_on_issue(repo: str, number: int, body: str) -> Any:
        """Comment on an issue as the token owner. Needs: write."""
        return gate.run("comment_on_issue", repo, {"number": number, "body": body},
                        lambda gh: gh.comment_on_issue(repo, number, body))

    return mcp


def main() -> None:
    policy = Policy.load(os.environ.get("POLICY_FILE"))
    token = os.environ.get("GITHUB_TOKEN", "")
    github = GitHub(token) if token else None
    audit = AuditLog(os.environ.get("AUDIT_LOG", "audit.jsonl"))
    build_server(Gate(policy, github, audit)).run()


if __name__ == "__main__":
    main()
