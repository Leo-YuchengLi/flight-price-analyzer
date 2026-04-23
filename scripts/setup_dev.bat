@echo off
REM One-click dev environment setup for Windows.
REM Run once after cloning the repo.  Then use "npm run dev" to start.
REM
REM What this does:
REM   1. Check Node.js (>=18) and Python (>=3.11)
REM   2. Install npm dependencies
REM   3. Create backend\.venv and install Python packages
REM   4. Download Playwright Chromium into resources\pw-browsers\
REM
REM Usage: Double-click or run from Command Prompt:
REM   scripts\setup_dev.bat

setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1

set SCRIPT_DIR=%~dp0
set PROJECT_ROOT=%SCRIPT_DIR%..
set BACKEND_DIR=%PROJECT_ROOT%\backend

echo.
echo ==========================================
echo   航班价格分析工具  -- Dev Setup (Windows)
echo ==========================================
echo.

REM ── 1. Check Node.js ──────────────────────────────────────────────────────────
echo [1/5] Checking Node.js...
where node >nul 2>&1
if errorlevel 1 (
    echo   ERROR: Node.js not found.
    echo   Install from https://nodejs.org ^(v18+^)
    pause & exit /b 1
)
for /f "tokens=*" %%v in ('node -e "process.stdout.write(process.versions.node)"') do set NODE_VER=%%v
for /f "tokens=1 delims=." %%m in ("%NODE_VER%") do set NODE_MAJOR=%%m
if %NODE_MAJOR% LSS 18 (
    echo   ERROR: Node.js v%NODE_VER% is too old. Need v18+.
    echo   Upgrade at https://nodejs.org
    pause & exit /b 1
)
echo   OK  Node.js v%NODE_VER%

REM ── 2. Check Python ───────────────────────────────────────────────────────────
echo [2/5] Checking Python...
set PYTHON=
for %%c in (python3.12 python3.11 python3 python) do (
    if "!PYTHON!"=="" (
        where %%c >nul 2>&1
        if not errorlevel 1 (
            for /f "tokens=2 delims= " %%v in ('%%c --version 2^>^&1') do (
                for /f "tokens=1,2 delims=." %%a in ("%%v") do (
                    if %%a==3 if %%b GEQ 11 set PYTHON=%%c
                )
            )
        )
    )
)
if "!PYTHON!"=="" (
    echo   ERROR: Python 3.11+ not found.
    echo   Install from https://www.python.org/downloads/
    pause & exit /b 1
)
for /f "tokens=*" %%v in ('!PYTHON! --version') do echo   OK  %%v

REM ── 3. npm install ────────────────────────────────────────────────────────────
echo [3/5] Installing npm packages...
cd /d "%PROJECT_ROOT%"
call npm install
if errorlevel 1 ( echo   ERROR: npm install failed & pause & exit /b 1 )
echo   OK  npm packages installed

REM ── 4. Python venv + deps ─────────────────────────────────────────────────────
echo [4/5] Setting up Python virtual environment...
if not exist "%BACKEND_DIR%\.venv" (
    echo   Creating .venv...
    !PYTHON! -m venv "%BACKEND_DIR%\.venv"
)
call "%BACKEND_DIR%\.venv\Scripts\activate.bat"
echo   Installing Python packages ^(this may take a minute^)...
pip install --upgrade pip --quiet
pip install -r "%BACKEND_DIR%\requirements.txt" --quiet
if errorlevel 1 ( echo   ERROR: pip install failed & pause & exit /b 1 )
echo   OK  Python packages installed

REM ── 5. Download Playwright Chromium ──────────────────────────────────────────
echo [5/5] Downloading Playwright Chromium ^(no system Chrome needed^)...
set PW_BROWSERS_DIR=%PROJECT_ROOT%\resources\pw-browsers
if not exist "%PW_BROWSERS_DIR%" mkdir "%PW_BROWSERS_DIR%"
dir /b "%PW_BROWSERS_DIR%" 2>nul | findstr /r "." >nul
if errorlevel 1 (
    echo   Downloading Chromium ^(~170 MB, one-time^)...
    set PLAYWRIGHT_BROWSERS_PATH=%PW_BROWSERS_DIR%
    playwright install chromium
    if errorlevel 1 ( echo   ERROR: Playwright install failed & pause & exit /b 1 )
    echo   OK  Chromium downloaded to resources\pw-browsers\
) else (
    echo   OK  Chromium already present
)

REM ── Done ──────────────────────────────────────────────────────────────────────
echo.
echo ==========================================
echo   Setup complete!
echo ==========================================
echo.
echo   Start dev server:    npm run dev
echo   Build Windows EXE:   npm run dist:win
echo.
pause
