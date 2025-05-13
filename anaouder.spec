# -*- mode: python; coding: utf-8 -*-

import platform
import os

ARCH = os.getenv("ARCH") or 'x86_64' # Set to 'x86_64', or 'arm64' or 'universal2' for macOS
DEBUG = True

print("Architecture set to", ARCH)

def get_lib_path(path):
    if platform.system() in ("Linux", "Darwin"):
        python_version = f"python{platform.python_version_tuple()[0]}.{platform.python_version_tuple()[1]}"
        venv_dir = '.venv-arm64' if ARCH=='arm64' else '.venv'
        return os.path.join(f"./{venv_dir}/lib/{python_version}/site-packages", path)
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
            (get_lib_path("PySide6/Qt/lib/*.dylib"), "."),
            (get_lib_path("PySide6/Qt/plugins/*"), "PySide6/Qt/plugins"),
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
        (get_lib_path("ostilhou/asr/*.tsv"), "ostilhou/asr"),
        (get_lib_path("ostilhou/hspell/*.txt"), "ostilhou/hspell"),
        (get_lib_path("ostilhou/hspell/hunspell-dictionary/br_FR.dic"), "ostilhou/hspell/hunspell-dictionary/"),
        (get_lib_path("ostilhou/hspell/hunspell-dictionary/br_FR.aff"), "ostilhou/hspell/hunspell-dictionary/"),
        ("./icons/back.png", "icons/"),
        ("./icons/previous.png", "icons/"),
        ("./icons/play-button.png", "icons/"),
        ("./icons/pause.png", "icons/"),
        ("./icons/next.png", "icons/"),
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
        ("./icons/folder.png", "icons/"),
    ],
    hiddenimports=[
        'src.lang.br',
        'src.lang.cy',
        'src.lang.fr',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtMultimedia'
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
    upx=True,	# Some kind of compression, lighter but slower
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
    icon=None,
    bundle_identifier='org.otilde.anaouder',
    info_plist={
        'NSPrincipalClass': 'NSApplication',
        'NSAppleScriptEnabled': False,
        'NSHighResolutionCapable': 'True',
        'LSMinimumSystemVersion': '10.13.0',
        'NSRequiresAquaSystemAppearance': 'False',  # Add this for proper menu integration
	    'CFBundleDisplayName': 'Anaouder',
        'CFBundleName': 'Anaouder',
        'CFBundleIdentifier': 'com.otilde.anaouder',
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleVersion': '1.0.0',
        'NSAppleScriptEnabled': False,
        'LSApplicationCategoryType': 'public.app-category.utilities',
    }
)
