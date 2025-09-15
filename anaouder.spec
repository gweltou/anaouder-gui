# -*- mode: python; coding: utf-8 -*-

import platform
import os

ARCH = os.getenv("ARCH") or 'x86_64' # Set to 'x86_64', or 'arm64' or 'universal2' for macOS
DEBUG = True if os.getenv("DEBUG") == 'True' else False

print("Architecture set to", ARCH)
print(f"{DEBUG=}")

def get_lib_path(path):
    if platform.system() in ("Linux", "Darwin"):
        python_version = f"python{platform.python_version_tuple()[0]}.{platform.python_version_tuple()[1]}"
        return os.path.join(f"./.venv/lib/{python_version}/site-packages", path)
    elif platform.system() == "Windows":
        return os.path.join("./.venv/Lib/site-packages", path)


def get_binaries():
    binaries = []
    if platform.system() == "Linux":
        binaries = [
            (get_lib_path("vosk/libvosk.so"), "vosk"),
            (get_lib_path("static_ffmpeg/bin/linux/*"), "static_ffmpeg/bin/linux"),
        ]
    elif platform.system() == "Darwin":
        binaries = [
            (get_lib_path("vosk/libvosk.dyld"), "vosk"),
            (get_lib_path("static_ffmpeg/bin/darwin/*"), "static_ffmpeg/bin/darwin"),
            #(get_lib_path("PySide6/Qt/lib/*.dylib"), "."),
            #(get_lib_path("PySide6/Qt/plugins/*"), "PySide6/Qt/plugins"),
        ]
    elif platform.system() == "Windows":
        binaries = [
            (get_lib_path("vosk/libvosk.dll"), "vosk"),
            (get_lib_path("static_ffmpeg/bin/win32/*"), "static_ffmpeg/bin/win32"),
        ]
    return binaries


a = Analysis(
    ['main.py'],
    pathex=[],
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
        ("./icons/del_segment.png", "icons/"),
        ("./icons/follow_playhead.png", "icons/"),

        ("./icons/anaouder_256.png", "icons/"),
        ("./icons/OTilde.png", "icons/"),
        ("./icons/logo_dizale_small.png", "icons/"),
        ("./icons/logo_rannvro_breizh.png", "icons/"),

        # Breton language specific files
        (get_lib_path("ostilhou/asr/*.tsv"), "ostilhou/asr"),
        (get_lib_path("ostilhou/dicts/*.tsv"), "ostilhou/dicts"),
        (get_lib_path("ostilhou/hspell/*.txt"), "ostilhou/hspell"),
        (get_lib_path("ostilhou/hspell/hunspell-dictionary/br_FR.dic"), "ostilhou/hspell/hunspell-dictionary/"),
        (get_lib_path("ostilhou/hspell/hunspell-dictionary/br_FR.aff"), "ostilhou/hspell/hunspell-dictionary/"),
    ],
    hiddenimports=[
        'src.lang.br',
        'src.lang.cy',
        'src.lang.fr',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)


"""
splash = Splash(
    "image.png",
    binaries=a.binaries,
    datas=a.datas,
    text_pos=(10, 50),
    text_size=12,
    text_color='black'
)
"""


exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Anaouder',
    debug=DEBUG,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,	# Some kind of compression, lighter but slower
    upx_exclude=[],
    runtime_tmpdir=None,
    console=DEBUG,
    disable_windowed_traceback=False,
    argv_emulation=True, # Needed by macOS, apparently
    target_arch=ARCH,
    codesign_identity=None,
    entitlements_file=None,
)

# macOS specific configurations
app = BUNDLE(
    exe,
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
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleVersion': '1.0.0',
        'LSApplicationCategoryType': 'public.app-category.utilities',
    }
)
