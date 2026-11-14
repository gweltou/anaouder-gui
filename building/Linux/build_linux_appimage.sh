#!/bin/bash
# Build Anaouder as an x86_64 AppImage.
# Run it from any directory, inside the Python environment used for the build.
# Needs building/Linux/appimagetool-x86_64.AppImage (https://github.com/AppImage/appimagetool/releases).

set -euo pipefail

APP_NAME="Anaouder"
DIST_DIR="dist"
BUILD_DIR="build"
LINUX_DIR="building/Linux"
APPIMAGETOOL="$LINUX_DIR/appimagetool-x86_64.AppImage"

# Work from the repository root, wherever the script is called from
cd "$(dirname "$0")/../.."

if [ ! -x "$APPIMAGETOOL" ]; then
  echo "ERROR: $APPIMAGETOOL not found or not executable" >&2
  exit 1
fi

# Single source of truth for the version number
VERSION=$(python -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])")
APPIMAGE_NAME="${APP_NAME}-${VERSION}-x86_64.AppImage"
echo "== BUILDING ${APP_NAME} ${VERSION} (AppImage) =="

# Install the package so its metadata (read at runtime by anaouder/version.py) matches pyproject.toml
pip install -e ".[build]"
# static_ffmpeg downloads its binaries on first use only; the spec file bundles them
python -c "import static_ffmpeg; static_ffmpeg.add_paths()"

# 1. Clean and Build
rm -rf "$BUILD_DIR" "$DIST_DIR"
pyside6-lrelease translations/anaouder_fr.ts -qm translations/anaouder_fr.qm
pyside6-lrelease translations/anaouder_br.ts -qm translations/anaouder_br.qm
pyinstaller anaouder.spec

echo "== PREPARING AppDir =="
# Temporary AppDir, removed on exit
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT
APPDIR="$TMP_DIR/$APP_NAME.AppDir"
mkdir "$APPDIR"
cp -a "$DIST_DIR/$APP_NAME/." "$APPDIR/"
cp icons/anaouder_256.png "$APPDIR/anaouder.png"
cp "$LINUX_DIR/Anaouder.desktop" "$APPDIR/"
ln -s "$APP_NAME" "$APPDIR/AppRun"

echo "== BUILDING AppImage =="
# ARCH and VERSION are read by appimagetool from the environment
ARCH=x86_64 VERSION="$VERSION" "$APPIMAGETOOL" "$APPDIR" "$DIST_DIR/$APPIMAGE_NAME"

echo "Done! Share '$DIST_DIR/$APPIMAGE_NAME'"
