# -*- mode: python ; coding: utf-8 -*-
import sys
import os

# Fix recursion limit for large applications
sys.setrecursionlimit(sys.getrecursionlimit() * 10)

block_cipher = None

# Get project root (current directory when running PyInstaller)
project_root = os.getcwd()

# Collect all necessary data files
datas = [
    # Config
    ('config', 'config'),
    # Updates file (if available locally during build, else omitted)
    ('updates.json', '.'),
]

# Hidden imports for the application
hiddenimports = [
    'core',
    'ui',
    'scipy.special.cython_special',
    'win32timezone',
    'supabase',
    'gotrue',
    'postgrest',
    'realtime',
    'storage3',
    'functions',
    'hitem3d_api',  # Ensure our own modules are picked up if dynamic
    'core.supabase_client',
    'core.secret_manager',
]

a = Analysis(
    ['ui/desktop/app.py'],
    pathex=[project_root],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'test', 'pydoc'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ImageTo3DPro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ImageTo3DPro',
)
