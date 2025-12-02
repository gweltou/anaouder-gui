#!/bin/bash

APP_NAME="Anaouder"
DIST_DIR="dist"
BUILD_DIR="build"
VERSION="1.0"

# 1. Clean and Build
cd ../..
rm -rf $BUILD_DIR $DIST_DIR
pyinstaller anaouder.spec

echo "== AD-HOC SIGNING APP =="
# We sign the app with ad-hoc signature so it runs on ARM64
codesign --force --deep --sign - "$DIST_DIR/$APP_NAME.app"

echo "== PREPARING INSTALLER SCRIPTS =="
# Create a temporary folder for installer scripts
mkdir -p scripts

# Create the 'postinstall' script
# This script runs automatically after installation to fix the "Damaged" error
cat <<EOF > scripts/postinstall
#!/bin/bash
# Remove the quarantine flag from the installed app
xattr -cr "/Applications/$APP_NAME.app"
exit 0
EOF

# Make the script executable
chmod +x scripts/postinstall

echo "== BUILDING PACKAGE (.pkg) =="
# Create the installer package
# --root: The folder containing your App
# --install-location: Where to put it on the user's Mac
# --scripts: The folder containing the fix script

pkgbuild --root "$DIST_DIR/$APP_NAME.app" \
         --install-location "/Applications/$APP_NAME.app" \
         --scripts scripts \
         --identifier "com.anaouder.installer" \
         --version $VERSION \
         "$DIST_DIR/${APP_NAME}_${VERSION}_macOS-x86_Installer.pkg"

echo "Done! Share 'dist/${APP_NAME}_${VERSION}_macOS-x86_Installer.pkg'"
# Clean up temporary scripts
rm -rf scripts