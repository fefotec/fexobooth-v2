# -*- mode: python ; coding: utf-8 -*-
# FexoBooth PyInstaller Spec File
# Erstellt eine gebundelte EXE mit allen Dependencies

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Basis-Pfad
BASE_PATH = os.path.abspath('.')

# Sammle alle customtkinter Daten (Themes, etc.)
customtkinter_datas = collect_data_files('customtkinter')

# Sammle alle benötigten Submodule
hidden_imports = [
    'customtkinter',
    'PIL',
    'PIL._tkinter_finder',
    'cv2',
    'flask',
    'qrcode',
    'qrcode.image.pil',
    'psutil',
    'win32print',
    'win32api',
    'win32con',
    'pywintypes',
    'ctypes',
    'ctypes.wintypes',
]

# Asset-Dateien die eingepackt werden sollen
datas = [
    # Assets
    ('assets/icons', 'assets/icons'),
    ('assets/templates', 'assets/templates'),
    ('assets/videos', 'assets/videos'),

    # Konfiguration
    ('config.example.json', '.'),

    # Setup-Skripte
    ('setup', 'setup'),

    # Canon EDSDK DLLs (64-bit)
    ('EDSDK/EDSDKv132010W/EDSDKv132010W/Windows/EDSDK_64/Dll/EDSDK.dll', 'EDSDK'),
    ('EDSDK/EDSDKv132010W/EDSDKv132010W/Windows/EDSDK_64/Dll/EdsImage.dll', 'EDSDK'),
]

# Füge customtkinter Daten hinzu
datas.extend(customtkinter_datas)

# Binärdateien - OpenCV FFmpeg für Video-Playback
import site
cv2_path = None
for p in site.getsitepackages():
    test_path = os.path.join(p, 'cv2')
    if os.path.exists(test_path):
        cv2_path = test_path
        break

binaries = []
if cv2_path:
    # FFmpeg DLL für Video-Wiedergabe (kritisch!)
    for dll in os.listdir(cv2_path):
        if 'ffmpeg' in dll.lower() and dll.endswith('.dll'):
            binaries.append((os.path.join(cv2_path, dll), '.'))
            print(f"[INFO] Adding OpenCV FFmpeg DLL: {dll}")

a = Analysis(
    ['src/main.py'],
    pathex=[BASE_PATH],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'scipy',
        'numpy.testing',
        'pytest',
        'tkinter.test',
    ],
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
    name='FexoBooth',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Kein Konsolenfenster
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icons/camera.ico',  # App-Icon
    version_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='FexoBooth',
)
