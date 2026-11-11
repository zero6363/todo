# -*- mode: python ; coding: utf-8 -*-
"""轻待办打包配置：单文件、无控制台、剔除用不到的 Qt 组件。"""

from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []
for package in ("qfluentwidgets", "qframelesswindow"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

# 这些 Qt 组件本项目用不到，剔除后体积从 ~240MB 降到 ~100MB
BLOCK_WORDS = (
    "webengine",
    "qt6quick", "qt6qml", "qt6labs", "qt63d", "qt6charts", "qt6datavisualization",
    "qt6pdf", "qt6designer", "qt6help", "qt6uitools", "qt6test", "qt6remoteobjects",
    "qt6sensors", "qt6texttospeech", "qt6websockets", "qt6webchannel",
    "qt6virtualkeyboard", "qt6spatialaudio", "qt6statemachine",
    "icudtl.dat",
    "plugins\\qmltooling", "plugins\\sceneparsers", "plugins\\renderers",
    "plugins\\geometryloaders", "plugins\\assetimporters",
)


def keep(entry) -> bool:
    name = entry[0].replace("/", "\\").lower()
    return not any(word in name for word in BLOCK_WORDS)


a = Analysis(
    ["轻待办.pyw"],
    pathex=[],
    binaries=binaries,
    datas=datas + [("assets", "assets")],
    hiddenimports=hiddenimports + ["PySide6.QtSvg", "PySide6.QtSvgWidgets", "PySide6.QtXml"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "customtkinter", "pystray"],
    noarchive=False,
    optimize=0,
)
a.binaries = [item for item in a.binaries if keep(item)]
a.datas = [item for item in a.datas if keep(item)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="轻待办",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=["assets\\icon.ico"],
)
