#!/bin/bash
# install.sh
# Run this to set up the app. Safe to run more than once.
#
# Most Linux file managers won't run this on double-click by default.
# Testers may need to: right-click -> Properties -> Permissions -> "Allow executing file as program",
# then double-click and choose "Run" (not "Run in Terminal" - either works, but plain "Run" is fine).
# If double-click still just opens a text editor, open a terminal in this folder and run: ./install.sh

set -e

echo "=============================================="
echo " Installing the app - please wait..."
echo "=============================================="

if ! command -v python3 &> /dev/null; then
    echo ""
    echo "ERROR: Python 3 was not found on this system."
    echo "Please install it using your distribution's package manager (e.g. 'sudo apt install python3 python3-venv')"
    echo "and then run this script again."
    echo ""
    read -p "Press Enter to close this window..."
    exit 1
fi

echo "Found Python: $(python3 --version)"

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    if ! python3 -m venv .venv; then
        echo ""
        echo "ERROR: Could not create the virtual environment."
        echo "You may need to install the venv module, e.g.: sudo apt install python3-venv"
        echo ""
        read -p "Press Enter to close this window..."
        exit 1
    fi
else
    echo "Virtual environment already exists, reusing it."
fi

source .venv/bin/activate

echo "Upgrading pip..."
python3 -m pip install --upgrade pip --quiet

if [ -f "pyproject.toml" ]; then
    echo "Installing app and dependencies from pyproject.toml..."
    if ! python3 -m pip install .; then
        echo ""
        echo "ERROR: Installation from pyproject.toml failed (see messages above)."
        echo ""
        read -p "Press Enter to close this window..."
        exit 1
    fi
else
    echo "Missing pyproject.toml file"
    exit 1
fi

# Desktop file and filetype association

if command -v xdg-desktop-menu &> /dev/null && command -v xdg-mime &> /dev/null; then
    xdg-desktop-menu install --novendor building/Linux/Anaouder.desktop || \
        echo "  (Warning: could not install the desktop menu entry - not critical, the app will still run.)"
    xdg-mime install --novendor building/Linux/anaouder-ali_filetype.xml || \
        echo "  (Warning: could not install the custom MIME type - not critical, the app will still run.)"
    xdg-mime default Anaouder.desktop text/x-ali || true
    xdg-mime default Anaouder.desktop application/x-subrip || true
else
    echo "  (Skipping: xdg-desktop-menu/xdg-mime not found on this system - not critical, the app will still run.)"
fi


echo ""
echo "=============================================="
echo " Installation complete!"
echo " You can now run 'start.sh' to launch the app."
echo "=============================================="
echo ""
read -p "Press Enter to close this window..."
