import json
import pytest
from permissioned_github_mcp.policy import Policy, PermissionDenied


def test_default_is_read_only():
    p = Policy()
    p.check("list_issues", "a/b")
    with pytest.raises(PermissionDenied):
        p.check("add_labels", "a/b")


def test_repo_grant_includes_lower_scopes(tmp_path):
    f = tmp_path / "p.json"
    f.write_text(json.dumps({"repos": {"Me/Repo": {"scope": "triage"}}}))
    p = Policy.load(f)
    p.check("get_issue", "me/repo")      # read is inside triage
    p.check("close_issue", "me/repo")    # triage
    with pytest.raises(PermissionDenied):
        p.check("comment_on_issue", "me/repo")  # needs write


def test_no_default_blocks_unlisted_repos(tmp_path):
    f = tmp_path / "p.json"
    f.write_text(json.dumps({"default_scope": None, "repos": {}}))
    with pytest.raises(PermissionDenied):
        Policy.load(f).check("list_issues", "x/y")


def test_unknown_scope_rejected(tmp_path):
    f = tmp_path / "p.json"
    f.write_text(json.dumps({"repos": {"a/b": {"scope": "admin"}}}))
    with pytest.raises(ValueError):
        Policy.load(f)
