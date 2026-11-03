# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification file for NovaBank Enterprise Desktop System."""

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None
PROJECT_ROOT = Path(SPECPATH).parent.resolve()
SRC_DIR = PROJECT_ROOT / "src"

# Collect data files
datas = [
    (str(SRC_DIR / "novabank" / "ui" / "resources" / "styles.qss"), "novabank/ui/resources"),
]

if (PROJECT_ROOT / ".env.example").exists():
    datas.append((str(PROJECT_ROOT / ".env.example"), "."))

# Collect submodules and hidden imports
hiddenimports = [
    "pydantic",
    "pydantic.deprecated",
    "pydantic_settings",
    "sqlalchemy",
    "sqlalchemy.dialects.mysql",
    "sqlalchemy.dialects.sqlite",
    "pymysql",
    "keyring",
    "keyring.backends",
    "keyring.backends.Windows",
    "httpx",
    "novabank.infrastructure.db.models",
    "novabank.infrastructure.reporting.pdf_generator",
] + collect_submodules("novabank")

a = Analysis(
    [str(SRC_DIR / "novabank" / "main.py")],
    pathex=[str(SRC_DIR), str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "IPython", "notebook"],
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
    name="NovaBank",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # Windows GUI application
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
    upx=False,
    upx_exclude=[],
    name="NovaBank",
)

