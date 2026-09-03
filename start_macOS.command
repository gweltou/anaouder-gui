#!/bin/bash
# start.command
# Double-click this file to launch the app.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d ".venv" ]; then
    echo "It looks like the app hasn't been installed yet."
    echo "Please double-click 'install.command' first."
    echo ""
    read -p "Press Return to close this window..."
    exit 1
fi

source .venv/bin/activate

echo "Starting Anaouder in terminal mode..."
python3 ./main.py

# Keep the window open if the app crashes immediately, so testers can see the error
status=$?
if [ $status -ne 0 ]; then
    echo ""
    echo "The app closed with an error (exit code $status)."
    read -p "Press Return to close this window..."
fi
