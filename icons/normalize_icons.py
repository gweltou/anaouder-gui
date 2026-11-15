"""
Make uniform copies of the UI icons, in the `icons/toolbar/` folder.

The source PNG files come from various places: they have different sizes
and different amounts of transparent padding around the drawing.
This script crops each drawing to its visible part, centers it in a square
canvas and saves the result in `icons/toolbar/`. The source files are left
untouched. The application loads the icons from `icons/toolbar/`.

Grey and black icons are also converted to pure black with transparency
(a light grey pixel becomes a faint black pixel). They look the same on a
light background, and the application can turn them white for dark mode
by simply inverting their colors.

Usage, from the repository root:

    python icons/normalize_icons.py

Run it again after adding or changing an icon: add the source file
to `ICONS` below, with a scale factor if the drawing looks too big or
too heavy next to the others.
"""

from pathlib import Path

from PIL import Image


ICONS_DIR = Path(__file__).parent
OUTPUT_DIR = ICONS_DIR / "toolbar"
CANVAS_SIZE = 128

# Source file -> size of the drawing relative to the canvas (1.0 fills it)
ICONS = {
    "sparkles-yellow.png": 1.0,
    "play-button.png": 0.8,
    "pause.png": 0.75,
    "back.png": 0.8,
    "previous.png": 1.0,
    "next.png": 1.0,
    "endless-loop.png": 1.0,
    "zoom_in.png": 0.9,
    "zoom_out.png": 0.9,
    "diskette.png": 0.9,
    "undo.png": 1.0,
    "redo.png": 1.0,
    "italic.png": 0.75,
    "bold.png": 0.75,
    "newline.png": 0.9,
    "em_dashes.png": 0.9,
    "head-side-thinking.png": 1.0,
    "123-numbers.png": 0.9,
    "font.png": 0.9,
    "waveform.png": 1.0,
    "volume.png": 1.0,
    "rabbit-fast.png": 1.0,
    "folder.png": 1.0,
    "magnet.png": 1.0,
    "select_segment.png": 0.9,
    "add_segment.png": 0.9,
    "trash.png": 0.9,
    "follow_playhead.png": 1.0,
}


def is_monochrome(image: Image.Image) -> bool:
    """True if all the visible pixels are black, grey or white"""
    for r, g, b, a in image.getdata():
        if a > 0 and max(r, g, b) - min(r, g, b) > 16:
            return False
    return True


def to_black_with_alpha(image: Image.Image) -> Image.Image:
    """Turn the grey levels into the opacity of black pixels"""
    pixels = [
        (0, 0, 0, a * (255 - (r + g + b) // 3) // 255)
        for r, g, b, a in image.getdata()
    ]
    result = Image.new("RGBA", image.size)
    result.putdata(pixels)
    return result


def normalize(source: Path, scale: float) -> Image.Image:
    image = Image.open(source).convert("RGBA")
    bbox = image.getchannel("A").getbbox()
    if bbox:
        image = image.crop(bbox)

    side = round(CANVAS_SIZE * scale)
    image.thumbnail((side, side), Image.Resampling.LANCZOS)
    if image.width < side and image.height < side:
        # Small source files: scale up as well
        ratio = side / max(image.size)
        new_size = (round(image.width * ratio), round(image.height * ratio))
        image = image.resize(new_size, Image.Resampling.LANCZOS)

    if is_monochrome(image):
        image = to_black_with_alpha(image)

    canvas = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), (0, 0, 0, 0))
    canvas.paste(
        image,
        ((CANVAS_SIZE - image.width) // 2, (CANVAS_SIZE - image.height) // 2),
    )
    return canvas


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    for filename, scale in ICONS.items():
        normalize(ICONS_DIR / filename, scale).save(OUTPUT_DIR / filename)
        print(f"{filename} -> {OUTPUT_DIR.name}/{filename}")


if __name__ == "__main__":
    main()
