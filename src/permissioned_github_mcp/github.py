"""Thin GitHub REST client: clear errors, compact results."""

from __future__ import annotations

import datetime as dt

import httpx

API = "https://api.github.com"
BODY_LIMIT = 1500  # characters of an issue body returned to the agent


class GitHubError(Exception):
    pass


class GitHub:
    def __init__(self, token: str, client: httpx.Client | None = None):
        if not token:
            raise GitHubError(
                "GITHUB_TOKEN is not set. Create a fine-grained token limited to "
                "the repos you want the agent to touch."
            )
        self._client = client or httpx.Client(timeout=20)
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _request(self, method: str, path: str, **kwargs) -> dict | list:
        resp = self._client.request(method, API + path, headers=self._headers, **kwargs)
        if resp.status_code == 401:
            raise GitHubError("GitHub rejected the token (expired or revoked). Create a new one.")
        if resp.status_code == 403 and resp.headers.get("x-ratelimit-remaining") == "0":
            reset = int(resp.headers.get("x-ratelimit-reset", "0"))
            when = dt.datetime.fromtimestamp(reset, dt.timezone.utc).strftime("%H:%M UTC")
            raise GitHubError(f"GitHub rate limit reached. It resets at {when}.")
        if resp.status_code == 403:
            raise GitHubError("The token is not allowed to do this. Check its repo permissions.")
        if resp.status_code == 404:
            raise GitHubError("Not found, or the token cannot see this repo.")
        if resp.status_code >= 400:
            raise GitHubError(f"GitHub error {resp.status_code}: {resp.text[:200]}")
        return resp.json() if resp.content else {}

    # Compact shapes keep agent context small.
    @staticmethod
    def _issue_summary(i: dict) -> dict:
        return {
            "number": i["number"],
            "title": i["title"],
            "state": i["state"],
            "labels": [l["name"] for l in i.get("labels", [])],
            "author": (i.get("user") or {}).get("login"),
            "comments": i.get("comments", 0),
            "updated_at": i.get("updated_at"),
        }

    def list_issues(self, repo: str, state: str = "open", limit: int = 20) -> list[dict]:
        items = self._request(
            "GET", f"/repos/{repo}/issues", params={"state": state, "per_page": min(limit, 100)}
        )
        # The issues endpoint also returns pull requests; drop them.
        return [self._issue_summary(i) for i in items if "pull_request" not in i][:limit]

    def get_issue(self, repo: str, number: int) -> dict:
        i = self._request("GET", f"/repos/{repo}/issues/{number}")
        body = i.get("body") or ""
        out = self._issue_summary(i)
        out["body"] = body[:BODY_LIMIT] + ("... [truncated]" if len(body) > BODY_LIMIT else "")
        return out

    def add_labels(self, repo: str, number: int, labels: list[str]) -> dict:
        res = self._request("POST", f"/repos/{repo}/issues/{number}/labels", json={"labels": labels})
        return {"number": number, "labels": [l["name"] for l in res]}

    def close_issue(self, repo: str, number: int) -> dict:
        res = self._request("PATCH", f"/repos/{repo}/issues/{number}", json={"state": "closed"})
        return {"number": number, "state": res.get("state")}

    def comment_on_issue(self, repo: str, number: int, body: str) -> dict:
        res = self._request("POST", f"/repos/{repo}/issues/{number}/comments", json={"body": body})
        return {"number": number, "comment_url": res.get("html_url")}
