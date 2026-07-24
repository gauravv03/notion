#!/usr/bin/env bash
# Subscription-bridge setup: wire ChatGPT (Codex CLI) + Gemini (Gemini CLI)
# into Claude Code as MCP servers, using ONLY your existing subscriptions.
# No API keys. Run this ONCE on your LOCAL machine (not in a cloud sandbox —
# the logins need a browser).
#
# Prereqs: Node.js 20+, npm, and Claude Code installed (`claude --version`).
set -euo pipefail

bold() { printf '\033[1m%s\033[0m\n' "$*"; }

bold "== Step 1/4: Install Codex CLI (OpenAI) and Gemini CLI (Google) =="
npm install -g @openai/codex @google/gemini-cli gemini-mcp-tool

bold "== Step 2/4: Sign in with your ChatGPT subscription =="
echo "A browser window will open. Choose 'Sign in with ChatGPT' (NOT API key)."
codex login

bold "== Step 3/4: Sign in with your Google account (Gemini) =="
echo "When prompted, pick 'Login with Google'. Then type /quit to exit."
gemini || true

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

# Gemini CLI is bridged via the gemini-mcp-tool wrapper.
claude mcp add --scope user gemini -- npx -y gemini-mcp-tool

bold "== Done =="
echo "Verify with: claude mcp list   (both 'codex' and 'gemini' should show connected)"
echo "Then in any Claude Code session try:"
echo "  'Use the codex tool to review this diff, and ask gemini for a second opinion.'"
