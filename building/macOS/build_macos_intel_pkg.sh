#!/bin/bash
# Build Anaouder.app for Intel Macs (x86_64) and wrap it in a .pkg installer.
# Run it on an Intel Mac (or under Rosetta with an x86_64 Python), from any directory,
# inside the Python environment used for the build.

set -euo pipefail

ARCH="x86_64"
APP_NAME="Anaouder"
DIST_DIR="dist"
BUILD_DIR="build"

# Work from the repository root, wherever the script is called from
cd "$(dirname "$0")/../.."

# Single source of truth for the version number
VERSION=$(python -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])")
PKG_NAME="${APP_NAME}-${VERSION}_macOS-x86_Installer.pkg"
echo "== BUILDING ${APP_NAME} ${VERSION} (${ARCH}) =="

# Install the package so its metadata (read at runtime by anaouder/version.py) matches pyproject.toml
pip install -e ".[build]"
# static_ffmpeg downloads its binaries on first use only; the spec file bundles them
python -c "import static_ffmpeg; static_ffmpeg.add_paths()"

# 1. Clean and Build
rm -rf "$BUILD_DIR" "$DIST_DIR"
pyside6-lrelease translations/anaouder_fr.ts -qm translations/anaouder_fr.qm
pyside6-lrelease translations/anaouder_br.ts -qm translations/anaouder_br.qm
ARCH="$ARCH" pyinstaller anaouder.spec

echo "== AD-HOC SIGNING APP =="
# Not strictly required on Intel, but it gives the bundle a consistent signature
# (PyInstaller modifies binaries, which invalidates their original signatures)
codesign --force --deep --sign - "$DIST_DIR/$APP_NAME.app"

echo "== PREPARING INSTALLER SCRIPTS =="
# Temporary folder for the installer scripts, removed on exit
SCRIPTS_DIR=$(mktemp -d)
trap 'rm -rf "$SCRIPTS_DIR"' EXIT

# The 'postinstall' script runs after installation to fix the "Damaged" error
cat <<EOF > "$SCRIPTS_DIR/postinstall"
#!/bin/bash
# Remove the quarantine flag from the installed app
xattr -cr "/Applications/$APP_NAME.app"
exit 0
EOF
chmod +x "$SCRIPTS_DIR/postinstall"

echo "== BUILDING PACKAGE (.pkg) =="
# --root: the folder containing the app
# --install-location: where to put it on the user's Mac
# --scripts: the folder containing the fix script
pkgbuild --root "$DIST_DIR/$APP_NAME.app" \
         --install-location "/Applications/$APP_NAME.app" \
         --scripts "$SCRIPTS_DIR" \
         --identifier "com.OTilde.Anaouder" \
         --version "$VERSION" \
         "$DIST_DIR/$PKG_NAME"

echo "Done! Share '$DIST_DIR/$PKG_NAME'"
