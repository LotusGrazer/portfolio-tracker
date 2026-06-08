#!/bin/bash
# Launch Portfolio Tracker (macOS). Double-click in Finder, or drag to the Dock.
# Starts the local server and opens the app in your browser. Close this window
# (or press Ctrl-C) to stop it.
cd "$(dirname "$0")" || exit 1

URL="http://127.0.0.1:5000"

# First run? Set things up automatically.
if [ ! -d ".venv" ] || [ ! -f "frontend/dist/index.html" ]; then
  echo "First-time setup required — running setup…"
  ./setup.command || exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

# Start the server in the background, wait until it's ready, then open the browser.
python app.py &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null' EXIT

echo "Starting Portfolio Tracker…"
for _ in $(seq 1 40); do
  if curl -s "$URL/health" >/dev/null 2>&1; then break; fi
  sleep 0.5
done

open "$URL"
echo ""
echo "▶ Portfolio Tracker is running at $URL"
echo "  (Tip: bookmark that address. Re-open the app any time with start.command.)"
echo "  Close this window or press Ctrl-C to stop."
wait "$SERVER_PID"
