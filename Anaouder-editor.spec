# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[("./.venv/lib/python3.12/site-packages/vosk/libvosk.so", "vosk"),],
    datas=[
        ("./.venv/lib/python3.12/site-packages/ostilhou/asr/*.tsv", "ostilhou/asr"),
        ("./.venv/lib/python3.12/site-packages/ostilhou/hspell/*.txt", "ostilhou/hspell"),
        ("./.venv/lib/python3.12/site-packages/ostilhou/hspell/hunspell-dictionary/br_FR.dic", "ostilhou/hspell/hunspell-dictionary/"),
        ("./.venv/lib/python3.12/site-packages/ostilhou/hspell/hunspell-dictionary/br_FR.aff", "ostilhou/hspell/hunspell-dictionary/"),
        ("./icons/back.png", "icons/"),
        ("./icons/previous.png", "icons/"),
        ("./icons/play-button.png", "icons/"),
        ("./icons/next.png", "icons/"),
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
