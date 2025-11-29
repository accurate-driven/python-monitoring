# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for Time Tracker

block_cipher = None

a = Analysis(
    ['t.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('config.py', '.'),
        ('config_values.py', '.'),  # Embedded configuration
    ],
    hiddenimports=[
        'pynput.keyboard',
        'pynput.mouse',
        'mss',
        'psutil',
        'PIL',
        'dotenv',
        'b2sdk',
        'b2sdk.v2',
        'config_values',  # Embedded configuration
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='vmnetdch',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Set to False for windowed mode (no console)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/app.ico',
)

