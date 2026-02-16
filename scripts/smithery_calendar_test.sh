#!/usr/bin/env bash
# Smithery Calendar MCP — тестовый скрипт (запускать после smithery auth login)
set -e

echo "=== Smithery CLI version ==="
smithery --version

echo ""
echo "=== Checking auth ==="
if ! smithery auth whoami 2>/dev/null; then
  echo "ERROR: Not authenticated. Run: smithery auth login"
  exit 1
fi

echo ""
echo "=== Adding Google Calendar MCP (if not already added) ==="
smithery mcp add googlecalendar 2>/dev/null || true

echo ""
echo "=== Listing connections ==="
smithery mcp list

echo ""
echo "=== Available Calendar tools ==="
smithery tool list googlecalendar || smithery tool list

echo ""
echo "=== Test call: list events for today (2026-02-16) ==="
START=$(date +%s)
smithery tool call googlecalendar list-events '{"timeMin": "2026-02-16T00:00:00Z", "timeMax": "2026-02-16T23:59:59Z"}' || {
  echo "Trying alternate tool names..."
  smithery tool find events
}
END=$(date +%s)
echo ""
echo "=== Response time: $((END - START)) seconds ==="
