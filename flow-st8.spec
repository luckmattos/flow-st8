# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files


datas = [
    ('VERSION', '.'),
    ('assets/flow-st8-icon.png', 'assets'),
]
datas += collect_data_files('silero_vad', includes=['data/*'])
datas += collect_data_files('whisper', includes=['assets/*'])


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'ctypes', 'sounddevice', 'pyperclip', 'silero_vad.data',
        # backends/__init__.py imports these behind `if sys.platform == "win32"`;
        # list them so the analysis never has to guess the branch.
        'backends.windows.autostart',
        'backends.windows.hotkey',
        'backends.windows.injector',
        'backends.windows.overlay',
        'backends.windows.tray',
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
    [],
    exclude_binaries=True,
    name='flow-st8',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon='assets/icon.ico',
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='flow-st8',
)
