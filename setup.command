#!/bin/bash
# One-time setup for Portfolio Tracker (macOS). Double-click in Finder.
# Creates the Python environment, installs dependencies, and builds the frontend.
cd "$(dirname "$0")" || exit 1

echo "Setting up Portfolio Tracker…"
echo ""

# --- Python backend ---------------------------------------------------------
if [ ! -d ".venv" ]; then
  echo "Creating Python virtual environment…"
  python3 -m venv .venv || { echo "❌ Could not create .venv (is Python 3 installed?)"; exit 1; }
fi
# shellcheck disable=SC1091
source .venv/bin/activate
echo "Installing Python packages…"
pip install -q --upgrade pip >/dev/null 2>&1
pip install -q -r requirements.txt || { echo "❌ pip install failed"; exit 1; }

# --- Frontend build ---------------------------------------------------------
# Use a writable npm cache to sidestep root-owned ~/.npm cache issues.
export NPM_CONFIG_CACHE="${NPM_CONFIG_CACHE:-/tmp/pt-npm-cache}"
echo "Installing and building the frontend (this can take a minute)…"
( cd frontend && npm install && npm run build ) || { echo "❌ frontend build failed (is Node installed?)"; exit 1; }

echo ""
echo "✅ Setup complete. Launch the app by double-clicking start.command"
echo "   (you can drag it to your Desktop or Dock for easy access)."
echo ""
read -r -p "Press Return to close this window."
