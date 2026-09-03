#!/bin/bash
# install.command
# Double-click this file to set up the app. Safe to run more than once.

set -e

# Always work from the folder this script lives in, no matter where it's double-clicked from
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=============================================="
echo " Installing the app - please wait..."
echo "=============================================="

# 1. Make sure Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo ""
    echo "ERROR: Python 3 was not found on this Mac."
    echo "Please install it from https://www.python.org/downloads/ and then run this script again."
    echo ""
    read -p "Press Return to close this window..."
    exit 1
fi

echo "Found Python: $(python3 --version)"

# 2. Create the virtual environment if it doesn't already exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
else
    echo "Virtual environment already exists, reusing it."
fi

# 3. Activate it and install dependencies
source .venv/bin/activate

echo "Upgrading pip..."
python3 -m pip install --upgrade pip --quiet

if [ -f "pyproject.toml" ]; then
    echo "Installing app and dependencies from pyproject.toml..."
    if ! python3 -m pip install .; then
        echo ""
        echo "ERROR: Installation from pyproject.toml failed (see messages above)."
        echo ""
        read -p "Press Return to close this window..."
        exit 1
    fi
elif [ -f "requirements.txt" ]; then
    echo "Installing dependencies from requirements.txt..."
    python3 -m pip install -r requirements.txt
else
    echo "No pyproject.toml or requirements.txt found - installing PySide6 directly..."
    python3 -m pip install PySide6
fi

echo ""
echo "=============================================="
echo " Installation complete!"
echo " You can now double-click 'start.command' to launch the app."
echo "=============================================="
echo ""
read -p "Press Return to close this window..."
