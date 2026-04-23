#!/usr/bin/env bash
# Build the Python backend + bundle Playwright Chromium.
# Usage: ./scripts/build_backend.sh  (or: npm run build:backend)
# Output:
#   backend/dist/backend/     — PyInstaller bundle (copy to resources/backend/)
#   resources/pw-browsers/    — Playwright Chromium (bundled by electron-builder)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_ROOT/backend"
PW_BROWSERS_DIR="$PROJECT_ROOT/resources/pw-browsers"

echo "==> Activating venv…"
source "$BACKEND_DIR/.venv/bin/activate"

echo "==> Installing PyInstaller into venv…"
pip install pyinstaller --quiet

# ── Download Playwright Chromium into resources/pw-browsers/ ──────────────────
echo "==> Preparing Playwright Chromium in resources/pw-browsers/ …"
mkdir -p "$PW_BROWSERS_DIR"
if [ -z "$(ls -A "$PW_BROWSERS_DIR" 2>/dev/null)" ]; then
  echo "    Downloading (~170 MB, one-time)…"
  PLAYWRIGHT_BROWSERS_PATH="$PW_BROWSERS_DIR" playwright install chromium
else
  echo "    Already present, skipping download."
fi
echo "    Chromium at: $PW_BROWSERS_DIR"

# ── Locate packages needed for bundling ──────────────────────────────────────
PLAYWRIGHT_PKG=$(python -c "import playwright; import os; print(os.path.dirname(playwright.__file__))")
STEALTH_PKG=$(python -c "import playwright_stealth; import os; print(os.path.dirname(playwright_stealth.__file__))" 2>/dev/null || echo "")
echo "==> Playwright package: $PLAYWRIGHT_PKG"
[ -n "$STEALTH_PKG" ] && echo "==> playwright-stealth package: $STEALTH_PKG"

echo "==> Running PyInstaller…"
cd "$BACKEND_DIR"

pyinstaller \
  --name backend \
  --distpath dist \
  --workpath build_tmp \
  --noconfirm \
  --onedir \
  --hidden-import uvicorn.logging \
  --hidden-import uvicorn.lifespan.on \
  --hidden-import uvicorn.lifespan.off \
  --hidden-import uvicorn.protocols.http.auto \
  --hidden-import uvicorn.protocols.websockets.auto \
  --hidden-import uvicorn.loops.auto \
  --hidden-import fastapi \
  --hidden-import pydantic \
  --hidden-import google.genai \
  --hidden-import google.genai.types \
  --hidden-import pandas \
  --hidden-import openpyxl \
  --hidden-import jinja2 \
  --hidden-import playwright \
  --hidden-import playwright.sync_api \
  --hidden-import playwright.async_api \
  --hidden-import playwright_stealth \
  --add-data "$PLAYWRIGHT_PKG/driver:playwright/driver" \
  ${STEALTH_PKG:+--add-data "$STEALTH_PKG:playwright_stealth"} \
  --add-data "ai:ai" \
  --add-data "api:api" \
  --add-data "models:models" \
  --add-data "report:report" \
  --add-data "scraper:scraper" \
  main.py

# ── Copy backend to resources/ ────────────────────────────────────────────────
echo "==> Copying backend binary to resources/backend/ …"
rm -rf "$PROJECT_ROOT/resources/backend"
cp -r "$BACKEND_DIR/dist/backend" "$PROJECT_ROOT/resources/backend"

echo ""
echo "==> All done!"
echo "    Backend : resources/backend/"
echo "    Chromium: resources/pw-browsers/"
echo ""
echo "    Now run: npm run dist:mac"
echo ""
