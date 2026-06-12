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
# Don't just check the connection succeeds: macOS AirPlay Receiver also
# listens on port 5000 and answers (with an empty body) while Flask is still
# starting, which would open the browser too early — onto a blank page.
# Only proceed once the response is actually our health JSON.
for _ in $(seq 1 40); do
  if curl -s -m 2 "$URL/health" 2>/dev/null | grep -q '"ok"'; then break; fi
  sleep 0.5
done

open "$URL"
echo ""
echo "▶ Portfolio Tracker is running at $URL"
echo "  (Tip: bookmark that address. Re-open the app any time with start.command.)"
echo "  Close this window or press Ctrl-C to stop."
wait "$SERVER_PID"
