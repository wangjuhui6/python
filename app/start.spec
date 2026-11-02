# -*- mode: python ; coding: utf-8 -*-

import os

# llama-cpp 用 ctypes 按 llama_cpp/lib 找 dll，PyInstaller 不会自动收这些文件。
_llama_lib = os.path.join('venv', 'Lib', 'site-packages', 'llama_cpp', 'lib')
_llama_bins = []
_llama_dll_names = []
if os.path.isdir(_llama_lib):
    for _name in os.listdir(_llama_lib):
        if _name.lower().endswith('.dll'):
            _llama_bins.append((os.path.join(_llama_lib, _name), os.path.join('llama_cpp', 'lib')))
            _llama_dll_names.append(_name)

a = Analysis(
    ['start.py'],
    pathex=[],
    binaries=_llama_bins,
    datas=[
        ('html', 'html'),
        ('tools', 'tools'),
        ('icon.ico', '.'),
        ('docker-compose.yml', '.'),
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

# True：显示控制台方便排查；False：不弹出黑框（托盘应用）
debug = False

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Map Tool',
    debug=debug,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=_llama_dll_names,
    runtime_tmpdir=None,
    console=debug,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
