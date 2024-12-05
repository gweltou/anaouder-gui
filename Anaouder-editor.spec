# -*- mode: python ; coding: utf-8 -*-

import platform

binaries = []
if platform.system() == "Linux":
    binaries = [
        ("./.venv/lib/python3.12/site-packages/vosk/libvosk.so", "vosk"),
        ("./.venv/lib/python3.12/site-packages/static_ffmpeg/bin/linux/*", "static_ffmpeg/bin/linux"),
    ]
elif platform.system() == "Darwin":
    binaries = [
        ("./.venv/lib/python3.12/site-packages/vosk/libvosk.dyld", "vosk"),
        ("./.venv/lib/python3.12/site-packages/static_ffmpeg/bin/darwin/*", "static_ffmpeg/bin/darwin"),
    ]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=[
        ("./.venv/lib/python3.12/site-packages/ostilhou/asr/*.tsv", "ostilhou/asr"),
        ("./.venv/lib/python3.12/site-packages/ostilhou/hspell/*.txt", "ostilhou/hspell"),
        ("./.venv/lib/python3.12/site-packages/ostilhou/hspell/hunspell-dictionary/br_FR.dic", "ostilhou/hspell/hunspell-dictionary/"),
        ("./.venv/lib/python3.12/site-packages/ostilhou/hspell/hunspell-dictionary/br_FR.aff", "ostilhou/hspell/hunspell-dictionary/"),
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
    hiddenimports=[],
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
    name='Anaouder-editor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
