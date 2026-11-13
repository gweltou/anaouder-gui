"""
macOs packaging:
  Comment out lines
"""

import importlib.util
import os
import platform
import tomllib
from importlib.metadata import version as installed_version

from PIL import Image, ImageDraw, ImageFont
from PyInstaller.utils.hooks import collect_data_files, copy_metadata

ARCH = os.getenv("ARCH") or 'x86_64' # Set to 'x86_64', or 'arm64' or 'universal2' for macOS
DEBUG = os.getenv("DEBUG") == 'True'
USE_UPX = False
ROOT = os.path.abspath(os.getcwd())

# Read the version from pyproject.toml so it doesn't depend on installed package metadata
with open(os.path.join(ROOT, "pyproject.toml"), "rb") as f:
    __version__ = tomllib.load(f)["project"]["version"]

# The app reads its version at runtime from the bundled package metadata (see anaouder/version.py),
# which comes from the installed package, not from pyproject.toml
if installed_version("anaouder-gui") != __version__:
    print(
        f"WARNING: installed anaouder-gui metadata is {installed_version('anaouder-gui')}, "
        f"pyproject.toml says {__version__}. Run `pip install -e .` before building."
    )

print("Architecture set to", ARCH)
print(f"{DEBUG=}")


def get_package_dir(package: str) -> str:
    """Locate an installed package, whatever the Python environment (venv, conda, system...)"""
    spec = importlib.util.find_spec(package)
    if spec is None or not spec.submodule_search_locations:
        raise SystemExit(f"ERROR: package '{package}' is not installed in this environment")
    return spec.submodule_search_locations[0]


def get_binaries():
    # libvosk is listed explicitly: on macOS the vosk wheel names it 'libvosk.dyld',
    # which PyInstaller's collect_dynamic_libs() would not pick up
    libvosk = {
        "Linux": "libvosk.so",
        "Darwin": "libvosk.dyld",
        "Windows": "libvosk.dll",
    }[platform.system()]
    ffmpeg_platform = {
        "Linux": "linux",
        "Darwin": "darwin",
        "Windows": "win32",
    }[platform.system()]

    # static_ffmpeg downloads its binaries on first use only:
    # run `python -c "import static_ffmpeg; static_ffmpeg.add_paths()"` once before building
    ffmpeg_dir = os.path.join(get_package_dir("static_ffmpeg"), "bin", ffmpeg_platform)
    if not os.path.isdir(ffmpeg_dir):
        raise SystemExit(
            f"ERROR: {ffmpeg_dir} not found. Run "
            "`python -c \"import static_ffmpeg; static_ffmpeg.add_paths()\"` first."
        )

    return [
        (os.path.join(get_package_dir("vosk"), libvosk), "vosk"),
        (os.path.join(ffmpeg_dir, "*"), f"static_ffmpeg/bin/{ffmpeg_platform}"),
    ]


a = Analysis(
    ['main.py'],
    pathex=[ROOT],
    binaries=get_binaries(),
    datas=[
        ("./icons/back.png", "icons/"),
        ("./icons/previous.png", "icons/"),
        ("./icons/play-button.png", "icons/"),
        ("./icons/pause.png", "icons/"),
        ("./icons/next.png", "icons/"),
        ("./icons/endless-loop.png", "icons/"),

        #("./icons/replay.png", "icons/"),
        ("./icons/sparkles-yellow.png", "icons/"),

        ("./icons/italic.png", "icons/"),
        ("./icons/bold.png", "icons/"),
        ("./icons/newline.png", "icons/"),
        ("./icons/em_dashes.png", "icons/"),

        ("./icons/zoom_in.png", "icons/"),
        ("./icons/zoom_out.png", "icons/"),

        ("./icons/head-side-thinking.png", "icons/"),
        ("./icons/123-numbers.png", "icons/"),
        ("./icons/font.png", "icons/"),
        ("./icons/waveform.png", "icons/"),
        ("./icons/volume.png", "icons/"),
        ("./icons/rabbit-fast.png", "icons/"),
        ("./icons/folder.png", "icons/"),

        ("./icons/undo.png", "icons/"),
        ("./icons/redo.png", "icons/"),

        ("./icons/magnet.png", "icons/"),
        ("./icons/select_segment.png", "icons/"),
        ("./icons/add_segment.png", "icons/"),
        ("./icons/trash.png", "icons/"),
        ("./icons/del_segment.png", "icons/"),
        ("./icons/follow_playhead.png", "icons/"),
		("./icons/led_green.png", "icons/"),
		("./icons/led_orange.png", "icons/"),
		("./icons/led_red.png", "icons/"),

        ("./icons/anaouder_256.png", "icons/"),
        ("./icons/OTilde.png", "icons/"),
        ("./icons/logo_dizale_small.png", "icons/"),
        ("./icons/logo_rannvro_breizh.png", "icons/"),
        ("./icons/logo_an_drouizig.png", "icons/"),

        # Translation files
        ("./translations/anaouder_br.qm", "translations/"),
        ("./translations/anaouder_fr.qm", "translations/"),

    ]
    + collect_data_files("ostilhou")  # Breton language data files (dictionaries, lexicons, hunspell...)
    + copy_metadata("anaouder-gui"),  # Needed by importlib.metadata in anaouder/version.py
    hiddenimports=[
        'anaouder.lang.br',
        'anaouder.lang.cy',
        'anaouder.lang.fr',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)


if platform.system() == "Darwin":
    # MAC OS BUILD
    # Without splash screen

    exe = EXE(
        pyz,
        a.scripts,
        exclude_binaries=True,
        name='Anaouder',
        debug=DEBUG,
        bootloader_ignore_signals=False,
        strip=False,
        upx=USE_UPX,	# Some kind of compression, lighter but slower
        upx_exclude=[],
        runtime_tmpdir=None,
        console=DEBUG,
        disable_windowed_traceback=False,
        argv_emulation=True, # Needed by macOS, apparently
        target_arch=ARCH,
    )

    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=USE_UPX,
        upx_exclude=[],
        name='Anaouder',
    )

    app = BUNDLE(
        coll,
        name='Anaouder.app',
        icon='icons/icon.icns',
        bundle_identifier='com.OTilde.Anaouder',
        info_plist={
            'CFBundleExecutable': 'Anaouder',
            'CFBundlePackageType': 'APPL',
            'NSPrincipalClass': 'NSApplication',
            'NSAppleScriptEnabled': False,
            'NSHighResolutionCapable': 'True',
            'LSMinimumSystemVersion': '10.13.0',
            'NSRequiresAquaSystemAppearance': 'False',
    	    'CFBundleDisplayName': 'Anaouder',
            'CFBundleName': 'Anaouder',
            'CFBundleIdentifier': 'com.OTilde.Anaouder',
            'CFBundleShortVersionString': __version__,
            'CFBundleVersion': __version__,
            'LSApplicationCategoryType': 'public.app-category.utilities',
        }
    )

else:
    # LINUX AND WINDOWS BUILD

    # Burn version number on copy of splash image
    splash_image = Image.open("icons/anaouder_splash.png", 'r')
    draw = ImageDraw.Draw(splash_image)
    draw.text(
        (splash_image.width - 32, 2),
        f"v{__version__}",
        font = ImageFont.load_default(14),
        fill = "#000000",
    )
    # Saved in PyInstaller's work directory (build/anaouder/), never in the source tree.
    # `workpath` is provided by PyInstaller in the spec namespace.
    os.makedirs(workpath, exist_ok=True)
    splash_path = os.path.join(workpath, "anaouder_splash_ver.png")
    splash_image.save(splash_path)

    splash = Splash(
        splash_path,
        binaries=a.binaries,
        datas=a.datas,
        text_pos=(516, 134),
        text_size=12,
        text_color='black',
        text_default='O kargañ...',
    )

    exe = EXE(
        pyz,
        a.scripts,
        splash,
        splash.binaries,
        exclude_binaries=True,
        name='Anaouder',
        debug=DEBUG,
        icon='icons/anaouder.ico' if platform.system() == "Windows" else None,
        bootloader_ignore_signals=False,
        strip=False,
        upx=USE_UPX,	# Some kind of compression, lighter but slower
        upx_exclude=[],
        runtime_tmpdir=None,
        console=DEBUG,
        disable_windowed_traceback=False,
        argv_emulation=True, # Needed by macOS, apparently
        target_arch=ARCH,
    )

    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        splash.binaries,
        strip=False,
        upx=True,
        upx_exclude=[],
        name='Anaouder',
    )
