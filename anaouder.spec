# -*- mode: python ; coding: utf-8 -*-

import platform
import os

ARCH = os.getenv("ARCH") # Set to 'x86_64' or 'arm64' or 'universal2' for macOS


def get_lib_path(path):
    if platform.system() in ("Linux", "Darwin"):
        python_version = f"python{platform.python_version_tuple()[0]}.{platform.python_version_tuple()[1]}"
        venv_dir = '.venv-arm64' if ARCH=='arm64' else '.venv'
        return os.path.join(f"./{venv_dir}/lib/{python_version}/site-packages", path)
    elif platform.system() == "Windows":
        return os.path.join("./.venv/Lib/site-packages", path)

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

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
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
    ],
    hiddenimports=[
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

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Anaouder',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True, # Needed by macOS, apparently
    target_arch=ARCH,
    codesign_identity=None,
    entitlements_file=None,
)

app = BUNDLE(
    exe,
    name='Anaouder.app',
    icon=None,
    bundle_identifier='org.dizale.anaouder',
    info_plist={
        'NSPrincipalClass': 'NSApplication',
        'NSHighResolutionCapable': 'True',
        'LSMinimumSystemVersion': '10.13.0',
        'NSRequiresAquaSystemAppearance': 'False',  # Add this for proper menu integration
	'CFBundleDisplayName': 'Anaouder',
        'CFBundleName': 'Anaouder',
        'CFBundleIdentifier': 'com.yourdomain.anaouder',
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleVersion': '1.0.0',
        'NSAppleScriptEnabled': False,
        'LSApplicationCategoryType': 'public.app-category.utilities',
    }
)
