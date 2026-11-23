# permissioned-github-mcp

An MCP server that lets an AI agent triage GitHub issues, where every tool is a permission.

Giving an agent a GitHub token usually means giving it everything that token can do. This server puts a policy between the agent and the API: each tool needs a scope, each repo grants a scope, and anything not granted is refused before a request is ever sent.

## What it does

| Tool | Needs | What it does |
| --- | --- | --- |
| `list_issues` | read | Lists issues, pull requests filtered out |
| `get_issue` | read | One issue, body cut to 1,500 characters |
| `add_labels` | triage | Adds labels |
| `close_issue` | triage | Closes an issue |
| `comment_on_issue` | write | Comments as the token owner |

Scopes stack: `triage` includes `read`, `write` includes both.

## Design choices

**Every tool is a permission.** The policy file grants a scope per repo, with a read-only default. A denied call returns a plain reason the agent can show the user, and never reaches GitHub.

**Writes start as dry runs.** With `dry_run_writes: true` (the default), write tools return what they would have done. You turn real writes on only once you trust the setup.

**Whose identity?** The agent acts as whoever owns the token. So use a fine-grained token limited to the repos in your policy. The policy then narrows it further, per tool. For a server used by many people, the next step would be a GitHub App with per-user tokens.

**Small context.** Issues come back as compact summaries (number, title, state, labels, author, comment count). Long bodies are truncated. Agents read less and cost less.

**Clear failures.** Expired tokens, missing access and rate limits each return a specific message (including when the rate limit resets), not a raw error.

**Audit log.** Every call is written to `audit.jsonl`: tool, repo, arguments, and whether it was allowed, denied, dry run or errored. The token is never logged.

## Setup

```bash
pip install -e ".[dev]"
cp policy.example.json policy.json   # then edit the repo names
```

Create a fine-grained token at GitHub, Settings, Developer settings, limited to your test repo, with Issues read and write.

Add it to Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "permissioned-github": {
      "command": "permissioned-github-mcp",
      "env": {
        "GITHUB_TOKEN": "your-token",
        "POLICY_FILE": "/full/path/to/policy.json",
        "AUDIT_LOG": "/full/path/to/audit.jsonl"
      }
    }
  }
}
```

Then try: "List the open issues in my-user/my-repo and label the bugs." With the example policy, labels come back as a dry run.

## Policy file

```json
{
  "default_scope": "read",
  "dry_run_writes": true,
  "repos": {
    "your-username/your-sandbox-repo": { "scope": "triage" }
  }
}
```

Set `default_scope` to `null` to block every repo you haven't listed.

## Tests

```bash
pytest
```

The tests mock GitHub and check the parts that matter: denied calls never send a request, dry runs never write, errors are readable, and the token never reaches the log.

## What's next

- GitHub App auth, so each user acts as themselves
- A "propose, then approve" mode where writes wait for a human click
- Per-tool rate limits, so one runaway agent can't burn the whole quota
