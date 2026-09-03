#!/bin/bash
# start.sh
# Run this to launch the app.
#
# If double-click doesn't work, open a terminal in this folder and run: ./start.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d ".venv" ]; then
    echo "It looks like the app hasn't been installed yet."
    echo "Please run 'install.sh' first."
    echo ""
    read -p "Press Enter to close this window..."
    exit 1
fi

source .venv/bin/activate

echo "Starting Anaouder in terminal mode..."
python3 ./main.py

status=$?
if [ $status -ne 0 ]; then
    echo ""
    echo "The app closed with an error (exit code $status)."
    read -p "Press Enter to close this window..."
fi
