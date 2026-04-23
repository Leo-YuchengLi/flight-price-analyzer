# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('/Users/yucheng/Desktop/flight-price-analyzer/backend/.venv/lib/python3.11/site-packages/playwright/driver', 'playwright/driver'), ('/Users/yucheng/Desktop/flight-price-analyzer/backend/.venv/lib/python3.11/site-packages/playwright_stealth', 'playwright_stealth'), ('ai', 'ai'), ('api', 'api'), ('models', 'models'), ('report', 'report'), ('scraper', 'scraper')],
    hiddenimports=['uvicorn.logging', 'uvicorn.lifespan.on', 'uvicorn.lifespan.off', 'uvicorn.protocols.http.auto', 'uvicorn.protocols.websockets.auto', 'uvicorn.loops.auto', 'fastapi', 'pydantic', 'google.genai', 'google.genai.types', 'pandas', 'openpyxl', 'jinja2', 'playwright', 'playwright.sync_api', 'playwright.async_api', 'playwright_stealth'],
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
    name='backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
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
    name='backend',
)
