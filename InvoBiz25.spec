# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('C:\\Users\\nanag\\AppData\\Roaming\\Python\\Python314\\site-packages\\customtkinter', 'customtkinter')]
binaries = []
hiddenimports = ['customtkinter', 'reportlab', 'PIL', 'PIL.Image', 'PIL.ImageDraw', 'PIL.ImageFont', 'sqlite3', 'json', 'calendar', 'platform', 'tempfile', 'subprocess']
tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PIL._avif', 'PIL._webp', 'PIL.FtImagePlugin', 'PIL.SgiImagePlugin', 'PIL.SpiderImagePlugin', 'matplotlib', 'numpy', 'pandas'],
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
    name='InvoBiz25',
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
    icon=['invobiz25.ico'],
)
