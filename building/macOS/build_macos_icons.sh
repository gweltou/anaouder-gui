#!/bin/bash
# Regenerate icons/icon.icns (used by anaouder.spec) from icons/anaouder_256.png.
# macOS only (iconutil). Needs ImageMagick (`magick`, or `convert` for ImageMagick 6).

set -euo pipefail

cd "$(dirname "$0")/../.."

SOURCE="icons/anaouder_256.png"
OUTPUT="icons/icon.icns"

if command -v magick >/dev/null; then
  IM="magick"
else
  IM="convert"
fi

# iconutil requires a folder whose name ends in '.iconset'
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT
ICONSET="$TMP_DIR/icon.iconset"
mkdir "$ICONSET"

# iconutil only accepts these names: icon_{16,32,128,256,512}x{same}[@2x].png
# The source is 256 px, so icon_256x256@2x and icon_512x512 can't be made without upscaling
for size in 16 32 128 256; do
  "$IM" "$SOURCE" -resize "${size}x${size}" "$ICONSET/icon_${size}x${size}.png"
  double=$((size * 2))
  if [ "$double" -le 256 ]; then
    "$IM" "$SOURCE" -resize "${double}x${double}" "$ICONSET/icon_${size}x${size}@2x.png"
  fi
done

iconutil -c icns "$ICONSET" -o "$OUTPUT"
echo "Written $OUTPUT"
