@echo off
REM Build the Python backend + bundle Playwright Chromium.
REM Usage: scripts\build_backend_win.bat  (or: npm run build:backend:win)
REM Output:
REM   backend\dist\backend\     — PyInstaller bundle
REM   resources\pw-browsers\    — Playwright Chromium

setlocal EnableDelayedExpansion

set SCRIPT_DIR=%~dp0
set PROJECT_ROOT=%SCRIPT_DIR%..
set BACKEND_DIR=%PROJECT_ROOT%\backend
set PW_BROWSERS_DIR=%PROJECT_ROOT%\resources\pw-browsers

echo =^> Activating venv...
call "%BACKEND_DIR%\.venv\Scripts\activate.bat"

echo =^> Installing PyInstaller...
pip install pyinstaller --quiet

REM ── Download Playwright Chromium ──────────────────────────────────────────────
echo =^> Downloading Playwright Chromium into resources\pw-browsers\ ...
if not exist "%PW_BROWSERS_DIR%" mkdir "%PW_BROWSERS_DIR%"
set PLAYWRIGHT_BROWSERS_PATH=%PW_BROWSERS_DIR%
playwright install chromium
echo     Chromium downloaded to: %PW_BROWSERS_DIR%

REM ── Build Python backend ──────────────────────────────────────────────────────
for /f "delims=" %%i in ('python -c "import playwright, os; print(os.path.dirname(playwright.__file__))"') do set PLAYWRIGHT_PKG=%%i
echo =^> Playwright package: %PLAYWRIGHT_PKG%

echo =^> Running PyInstaller...
cd /d "%BACKEND_DIR%"

pyinstaller ^
  --name backend ^
  --distpath dist ^
  --workpath build_tmp ^
  --noconfirm ^
  --onedir ^
  --hidden-import uvicorn.logging ^
  --hidden-import uvicorn.lifespan.on ^
  --hidden-import uvicorn.lifespan.off ^
  --hidden-import uvicorn.protocols.http.auto ^
  --hidden-import uvicorn.protocols.websockets.auto ^
  --hidden-import uvicorn.loops.auto ^
  --hidden-import fastapi ^
  --hidden-import pydantic ^
  --hidden-import google.genai ^
  --hidden-import google.genai.types ^
  --hidden-import pandas ^
  --hidden-import openpyxl ^
  --hidden-import jinja2 ^
  --hidden-import playwright ^
  --hidden-import playwright.sync_api ^
  --hidden-import playwright.async_api ^
  --add-data "%PLAYWRIGHT_PKG%\driver;playwright\driver" ^
  --add-data "ai;ai" ^
  --add-data "api;api" ^
  --add-data "models;models" ^
  --add-data "report;report" ^
  --add-data "scraper;scraper" ^
  main.py

REM ── Copy backend to resources\ ────────────────────────────────────────────────
echo =^> Copying backend binary to resources\backend\ ...
if exist "%PROJECT_ROOT%\resources\backend" rmdir /S /Q "%PROJECT_ROOT%\resources\backend"
xcopy /E /I "%BACKEND_DIR%\dist\backend" "%PROJECT_ROOT%\resources\backend"

echo.
echo =^> All done!
echo     Backend : resources\backend\
echo     Chromium: resources\pw-browsers\
echo.
echo     Now run: npm run dist:win
echo.
