# -*- mode: python ; coding: utf-8 -*-
"""Optimized PyInstaller spec for Shocking-VRChat (FastAPI + Uvicorn)."""

import sys
from pathlib import Path

block_cipher = None
ROOT = Path(SPECPATH)

a = Analysis(
    ['shocking_vrchat.py'],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        ('static', 'static'),
        ('templates', 'templates'),
        ('shocking_vrchat.ico', '.'),
        # wave_presets NOT bundled: kept as external files next to exe for easy editing
    ],
    hiddenimports=[
        # FastAPI / Starlette / Uvicorn
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'starlette.responses',
        'starlette.routing',
        'starlette.middleware',
        'starlette.middleware.errors',
        'multipart',
        'multipart.multipart',
        # Pydantic
        'pydantic',
        'pydantic_core',
        'annotated_types',
        # Our modules
        'srv',
        'srv.connector',
        'srv.connector.coyotev3ws',
        'srv.handler',
        'srv.handler.shock_handler',
        'srv.command_queue',
        'srv.wave_preset',
        'pulse_to_hex',
        'pulse_to_hex.dglab_pulse_converter',
        # OSC
        'pythonosc',
        'pythonosc.osc_server',
        'pythonosc.dispatcher',
        'pythonosc.udp_client',
        # Websockets
        'websockets',
        'websockets.server',
        'websockets.asyncio',
        'websockets.asyncio.server',
        # System tray
        'pystray',
        'pystray._win32',
        'PIL',
        'PIL.Image',
        'PIL.ImageDraw',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Test frameworks
        'pytest', 'unittest', '_pytest',
        # Development tools
        'setuptools', 'pip', 'wheel', 'pkg_resources',
        # Unused stdlib
        'tkinter', '_tkinter', 'turtle',
        'doctest', 'pdb', 'profile', 'cProfile',
        'xmlrpc', 'ftplib', 'imaplib', 'smtplib', 'poplib',
        'sqlite3',
        # IPython / Jupyter
        'IPython', 'jupyter', 'notebook',
        # Other unused
        'numpy', 'matplotlib', 'cv2', 'scipy',
        'pandas', 'sklearn', 'torch', 'tensorflow',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='shocking_vrchat',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon='shocking_vrchat.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='shocking_vrchat',
)
