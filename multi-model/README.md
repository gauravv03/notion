# Multi-model bridge: ChatGPT + Gemini inside Claude Code, subscription-only

Harness ChatGPT (Plus) and Gemini (Google account) **inside Claude Code** on hard,
effort-intensive tasks — paid for entirely by subscriptions you already own.
No API keys, no per-token billing.

## How it works

```
You ──► Claude Code (Opus/Fable — orchestrator)
              │
              ├─► codex MCP       ──► Codex CLI ──► "Sign in with ChatGPT" (your Plus plan)
              └─► antigravity MCP ──► Antigravity CLI (agy) ─► Google OAuth (your account/sub)
```

Both vendors ship official CLIs that authenticate with your *subscription* instead of
an API key — this is their sanctioned use, not a hack. Codex exposes an MCP server
mode natively; Antigravity is bridged via a small wrapper around its `agy -p`
headless mode. Claude Code speaks MCP natively and stays the driver, consulting
them as tools.

> **Why Antigravity, not Gemini CLI?** Google retired Gemini CLI for individual
> accounts on 2026-06-18 ("migrate to the Antigravity suite" error). Antigravity
> CLI is its official successor and still signs in with your Google account.

## Setup (once, on your local machine)

The logins are interactive browser OAuth flows, so this must run locally —
not in a cloud/web sandbox.

```bash
./setup.sh
```

That script: installs both CLIs → walks you through both logins → registers both
as user-scoped MCP servers in Claude Code. Verify afterwards with `claude mcp list`.

Then paste `CLAUDE-snippet.md` into your `~/.claude/CLAUDE.md` (applies everywhere)
or a project `CLAUDE.md` — it teaches Claude *when* to delegate: cross-model review
on hard tasks, Antigravity/Gemini for huge-context and grunt work, no delegation
on trivia.

## Using it

Explicit:

> Use codex to review this diff, and get antigravity's take too. Reconcile.

Or just work normally — with the CLAUDE.md rules in place, Claude will pull in
second opinions on hard tasks on its own.

## What this covers — and doesn't

| Capability | Covered? |
|---|---|
| GPT-5-class coding/reasoning via ChatGPT Plus | ✅ |
| Gemini Pro-class reasoning, ~1M-token context | ✅ |
| Cross-model consensus/review on hard tasks | ✅ |
| Cost: extra per-token billing | ✅ none — subscription allowances |
| Image/video generation (Sora, Veo, Imagen) | ❌ separate products; not exposed by these CLIs |

## Caveats

- **Shared rate limits**: Codex usage draws from the same allowance as your ChatGPT
  chats. Heavy agent use can exhaust it; it resets on the plan's cycle.
- **Antigravity quotas**: some AI Pro subscribers report a "Starter Quota" in
  Antigravity while Google sorts out entitlements — no extra billing either way,
  but the allowance may be smaller than the old Gemini CLI's.
- **Antigravity runs permissions auto-approved** in headless mode (so calls don't
  hang). Keep it advisory — Claude is the only agent that writes to the repo.
- **Keep it official**: proxy projects exist that wrap these CLIs into fake API
  endpoints for other tools. That's ToS-gray and risks account bans — the setup
  here sticks to each vendor's supported path.
