#!/usr/bin/env bash
# Subscription-bridge setup: wire ChatGPT (Codex CLI) + Google (Antigravity CLI)
# into Claude Code as MCP servers, using ONLY your existing subscriptions.
# No API keys. Run this ONCE on your LOCAL machine (not in a cloud sandbox —
# the logins need a browser).
#
# NOTE: Google retired the old Gemini CLI for individual accounts on
# 2026-06-18; Antigravity CLI (agy) is its official successor.
#
# Prereqs: Node.js 20+, npm, curl, and Claude Code installed (`claude --version`).
set -euo pipefail

bold() { printf '\033[1m%s\033[0m\n' "$*"; }

bold "== Step 1/4: Install Codex CLI (OpenAI) and Antigravity CLI (Google) =="
npm install -g @openai/codex
curl -fsSL https://antigravity.google/cli/install.sh | bash

bold "== Step 2/4: Sign in with your ChatGPT subscription =="
echo "A browser window will open. Choose 'Sign in with ChatGPT' (NOT API key)."
codex login

bold "== Step 3/4: Sign in with your Google account (Antigravity) =="
echo "When prompted, sign in with Google. Then exit the agy UI."
agy || true

bold "== Step 4/4: Register both as MCP servers in Claude Code =="
# Codex ships a native MCP server mode; the subcommand name varies by version.
if codex mcp-server --help >/dev/null 2>&1; then
  claude mcp add --scope user codex -- codex mcp-server
elif codex mcp serve --help >/dev/null 2>&1; then
  claude mcp add --scope user codex -- codex mcp serve
else
  echo "Could not detect Codex MCP server mode; check 'codex --help' and add manually:"
  echo "  claude mcp add --scope user codex -- codex <mcp-subcommand>"
fi

# Antigravity is bridged via a community wrapper around 'agy -p' headless mode.
claude mcp remove gemini 2>/dev/null || true   # clean up any dead Gemini CLI entry
claude mcp add --scope user antigravity -- npx -y antigravity-claude-mcp

bold "== Done =="
echo "Verify with: claude mcp list   ('codex' and 'antigravity' should show connected)"
echo "Then in any Claude Code session try:"
echo "  'Use the codex tool to review this diff, and ask antigravity for a second opinion.'"
