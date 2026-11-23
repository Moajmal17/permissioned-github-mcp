import json
import httpx
import respx
from permissioned_github_mcp.audit import AuditLog
from permissioned_github_mcp.github import GitHub
from permissioned_github_mcp.policy import Policy
from permissioned_github_mcp.server import Gate

API = "https://api.github.com"


def make(tmp_path, dry_run=True, scope="triage"):
    policy = Policy(repos={"me/repo": scope}, default_scope="read", dry_run_writes=dry_run)
    log = tmp_path / "audit.jsonl"
    return Gate(policy, GitHub("t0ken"), AuditLog(log)), log


def lines(log):
    return [json.loads(l) for l in log.read_text().splitlines()]


@respx.mock
def test_list_issues_is_compact_and_drops_prs(tmp_path):
    respx.get(f"{API}/repos/me/repo/issues").mock(return_value=httpx.Response(200, json=[
        {"number": 1, "title": "Bug", "state": "open", "labels": [{"name": "bug"}],
         "user": {"login": "a"}, "comments": 2, "updated_at": "2026-11-01", "body": "x" * 5000},
        {"number": 2, "title": "PR", "state": "open", "labels": [], "pull_request": {}},
    ]))
    gate, log = make(tmp_path)
    out = gate.run("list_issues", "me/repo", {}, lambda gh: gh.list_issues("me/repo"))
    assert out == [{"number": 1, "title": "Bug", "state": "open", "labels": ["bug"],
                    "author": "a", "comments": 2, "updated_at": "2026-11-01"}]
    assert lines(log)[0]["outcome"] == "allowed"


def test_denied_call_never_reaches_github(tmp_path):
    gate, log = make(tmp_path)
    with respx.mock(assert_all_called=False) as router:
        route = router.post(f"{API}/repos/me/repo/issues/1/comments")
        out = gate.run("comment_on_issue", "me/repo", {"number": 1},
                       lambda gh: gh.comment_on_issue("me/repo", 1, "hi"))
        assert not route.called
    assert "needs 'write'" in out["error"]
    assert lines(log)[0]["outcome"] == "denied"


def test_dry_run_write_makes_no_request(tmp_path):
    gate, log = make(tmp_path, dry_run=True)
    with respx.mock(assert_all_called=False) as router:
        route = router.post(f"{API}/repos/me/repo/issues/1/labels")
        out = gate.run("add_labels", "me/repo", {"number": 1, "labels": ["bug"]},
                       lambda gh: gh.add_labels("me/repo", 1, ["bug"]))
        assert not route.called
    assert out["dry_run"] is True
    assert lines(log)[0]["outcome"] == "dry_run"


@respx.mock
def test_live_write_when_allowed(tmp_path):
    respx.post(f"{API}/repos/me/repo/issues/1/labels").mock(
        return_value=httpx.Response(200, json=[{"name": "bug"}]))
    gate, _ = make(tmp_path, dry_run=False)
    out = gate.run("add_labels", "me/repo", {"number": 1, "labels": ["bug"]},
                   lambda gh: gh.add_labels("me/repo", 1, ["bug"]))
    assert out == {"number": 1, "labels": ["bug"]}


@respx.mock
def test_expired_token_and_rate_limit_messages(tmp_path):
    gate, log = make(tmp_path)
    respx.get(f"{API}/repos/me/repo/issues/5").mock(return_value=httpx.Response(401))
    out = gate.run("get_issue", "me/repo", {"number": 5}, lambda gh: gh.get_issue("me/repo", 5))
    assert "expired or revoked" in out["error"]
    respx.get(f"{API}/repos/me/repo/issues/6").mock(return_value=httpx.Response(
        403, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "0"}))
    out = gate.run("get_issue", "me/repo", {"number": 6}, lambda gh: gh.get_issue("me/repo", 6))
    assert "rate limit" in out["error"]
    assert "t0ken" not in log.read_text()  # token never logged


@respx.mock
def test_long_body_truncated(tmp_path):
    respx.get(f"{API}/repos/me/repo/issues/3").mock(return_value=httpx.Response(200, json={
        "number": 3, "title": "Long", "state": "open", "labels": [], "user": {"login": "a"},
        "body": "y" * 4000}))
    gate, _ = make(tmp_path)
    out = gate.run("get_issue", "me/repo", {"number": 3}, lambda gh: gh.get_issue("me/repo", 3))
    assert out["body"].endswith("[truncated]") and len(out["body"]) < 1600
