# Multi-model delegation rules (paste into your ~/.claude/CLAUDE.md or project CLAUDE.md)

Two MCP-bridged models are available, funded by existing subscriptions (no per-token cost):
- `codex` — OpenAI's frontier coding model via my ChatGPT plan.
- `antigravity` — Google Gemini (via Antigravity CLI) on my Google account/AI Pro sub.

## When to delegate

- **Hard / high-stakes tasks** (architecture decisions, gnarly bugs, security-sensitive
  changes, big refactors): draft your approach first, then ask BOTH `codex` and `antigravity`
  to critique it. Reconcile disagreements yourself; surface unresolved ones to me.
- **Second opinion before finalizing** any non-trivial diff: send the diff to `codex`
  for review. Apply fixes you agree with; tell me what you rejected and why.
- **Very large inputs** (whole-repo analysis, long logs, big docs): prefer `antigravity` —
  its context window is larger and usage is effectively free.
- **Grunt work** (summarizing logs, first-pass triage, boilerplate exploration):
  prefer `antigravity` to conserve Claude tokens.
- **Simple, quick tasks**: don't delegate; overhead isn't worth it.

## Rules

- You (Claude) stay the orchestrator: you own the final answer, edits, and commits.
  Delegated models advise; they do not write to the repo.
- Never send secrets, tokens, or credentials to the delegated models.
- If a delegated tool errors or hits a rate limit (limits are shared with my chat
  usage), fall back to doing the work yourself and note that you did.
- On disagreement between models, prefer the answer backed by verifiable evidence
  (tests, docs, repro) — not majority vote.
