output_path=/tmp/output.iconset

# the convert command comes from imagemagick
for size in 16 32 64 128 256; do
  half="$(($size / 2))"
  convert icons/anaouder_256.png -resize x$size $output_path/icon_${size}x${size}.png
  convert icons/anaouder_256.png -resize x$size $output_path/icon_${half}x${half}@2x.png
done

iconutil -c icns $output_path
