# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller Spec-File für Fexobooth
====================================

Erstellt eine One-Folder-Distribution mit eingebettetem VLC.
Muss auf dem DEV-Laptop (Windows 11) ausgeführt werden.

Nutzung:
    pyinstaller fexobooth.spec

Oder über build.bat (empfohlen).
"""

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

# ─────────────────────────────────────────────
# VLC-Pfad ermitteln
# ─────────────────────────────────────────────

VLC_PATH = None

# 1. Umgebungsvariable
if os.environ.get("VLC_PATH"):
    VLC_PATH = os.environ["VLC_PATH"]

# 2. Standard-Installationspfade
if not VLC_PATH:
    for candidate in [
        r"C:\Program Files\VideoLAN\VLC",
        r"C:\Program Files (x86)\VideoLAN\VLC",
    ]:
        if os.path.isfile(os.path.join(candidate, "libvlc.dll")):
            VLC_PATH = candidate
            break

# 3. Registry (optional)
if not VLC_PATH:
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\VideoLAN\VLC"
        )
        VLC_PATH = winreg.QueryValueEx(key, "InstallDir")[0]
        winreg.CloseKey(key)
    except Exception:
        pass

if VLC_PATH and os.path.isdir(VLC_PATH):
    print(f"VLC gefunden: {VLC_PATH}")
else:
    print("WARNUNG: VLC nicht gefunden! Videos werden nur mit OpenCV-Fallback funktionieren.")
    print("Installiere VLC oder setze VLC_PATH Umgebungsvariable.")
    VLC_PATH = None

# ─────────────────────────────────────────────
# EDSDK-Pfad (Canon Kamera)
# ─────────────────────────────────────────────

EDSDK_PATH = None
for candidate in [
    os.path.join(SPECPATH, "EDSDK", "EDSDKv132010W", "EDSDKv132010W", "Windows", "EDSDK_64", "Dll"),
    r"C:\fexobooth\EDSDK_64\Dll",
]:
    if os.path.isfile(os.path.join(candidate, "EDSDK.dll")):
        EDSDK_PATH = candidate
        print(f"EDSDK gefunden: {EDSDK_PATH}")
        break

if not EDSDK_PATH:
    print("INFO: EDSDK nicht gefunden - Canon-Unterstützung deaktiviert")

# ─────────────────────────────────────────────
# Binaries sammeln
# ─────────────────────────────────────────────

binaries = []

# VLC-DLLs einbinden
if VLC_PATH:
    # Core-DLLs → vlc/ Unterverzeichnis
    binaries.append((os.path.join(VLC_PATH, "libvlc.dll"), "vlc"))
    binaries.append((os.path.join(VLC_PATH, "libvlccore.dll"), "vlc"))

    # Plugins → vlc/plugins/
    vlc_plugins = os.path.join(VLC_PATH, "plugins")
    if os.path.isdir(vlc_plugins):
        for root, dirs, files in os.walk(vlc_plugins):
            for f in files:
                if f.endswith(".dll"):
                    src = os.path.join(root, f)
                    rel = os.path.relpath(root, VLC_PATH)
                    binaries.append((src, os.path.join("vlc", rel)))

# EDSDK-DLLs einbinden
if EDSDK_PATH:
    for dll_name in ["EDSDK.dll", "EdsImage.dll"]:
        dll_file = os.path.join(EDSDK_PATH, dll_name)
        if os.path.isfile(dll_file):
            binaries.append((dll_file, "."))

# ─────────────────────────────────────────────
# Daten-Dateien sammeln
# ─────────────────────────────────────────────

datas = [
    ("assets", "assets"),
    ("config.example.json", "."),
    ("setup", "setup"),
]

# CustomTkinter hat eigene Assets (Themes, etc.)
ctk_datas, ctk_binaries, ctk_hiddenimports = collect_all("customtkinter")
datas += ctk_datas
binaries += ctk_binaries

# ─────────────────────────────────────────────
# Analysis
# ─────────────────────────────────────────────

a = Analysis(
    ["src/main.py"],
    pathex=[SPECPATH],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        "vlc",
        "customtkinter",
        "cv2",
        "PIL",
        "PIL._tkinter_finder",
        "flask",
        "flask.json",
        "jinja2",
        "qrcode",
        "qrcode.image.svg",
        "win32print",
        "win32api",
        "pywintypes",
        "src",
        "src.app",
        "src.main",
        "src.config",
        "src.config.config",
        "src.config.defaults",
        "src.camera",
        "src.camera.base",
        "src.camera.webcam",
        "src.camera.canon",
        "src.camera.edsdk",
        "src.filters",
        "src.filters.filters",
        "src.gallery",
        "src.gallery.server",
        "src.gallery.qrcode_gen",
        "src.storage",
        "src.storage.local",
        "src.storage.usb",
        "src.storage.booking",
        "src.storage.statistics",
        "src.templates",
        "src.templates.loader",
        "src.templates.renderer",
        "src.templates.default",
        "src.ui",
        "src.ui.theme",
        "src.ui.screens",
        "src.ui.screens.start",
        "src.ui.screens.session",
        "src.ui.screens.filter",
        "src.ui.screens.final",
        "src.ui.screens.video",
        "src.ui.screens.admin",
        "src.utils",
        "src.utils.logging",
    ] + ctk_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "matplotlib",
        "scipy",
        "numpy.testing",
        "unittest",
        "pytest",
        "IPython",
        "notebook",
        "tkinter.test",
    ],
    noarchive=False,
)

# ─────────────────────────────────────────────
# Build
# ─────────────────────────────────────────────

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # One-Folder-Modus
    name="fexobooth",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX kann Probleme mit VLC-DLLs machen
    console=False,  # Kein Konsolenfenster
    disable_windowed_traceback=False,
    icon="assets/icons/camera.png",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="fexobooth",
)
