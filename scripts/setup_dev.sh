#!/usr/bin/env bash
# One-click dev environment setup for macOS / Linux.
# Run once after cloning the repo.  Then use "npm run dev" to start.
#
# What this does:
#   1. Check Node.js (≥18) and Python (≥3.11)
#   2. Install npm dependencies
#   3. Create backend/.venv and install Python packages
#   4. Download Playwright Chromium into resources/pw-browsers/
#
# Usage:
#   chmod +x scripts/setup_dev.sh
#   ./scripts/setup_dev.sh

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✓ $*${NC}"; }
warn() { echo -e "${YELLOW}  ⚠ $*${NC}"; }
err()  { echo -e "${RED}  ✗ $*${NC}"; exit 1; }
step() { echo -e "\n${BLUE}══ $* ══${NC}"; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_ROOT/backend"

echo ""
echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   航班价格分析工具  — Dev Setup         ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"

# ── 1. Check Node.js ──────────────────────────────────────────────────────────
step "Checking Node.js"
if ! command -v node &>/dev/null; then
  err "Node.js not found. Install from https://nodejs.org (v18+)"
fi
NODE_VER=$(node -e "process.stdout.write(process.versions.node)")
NODE_MAJOR="${NODE_VER%%.*}"
if [ "$NODE_MAJOR" -lt 18 ]; then
  err "Node.js v$NODE_VER is too old. Need v18+. Upgrade at https://nodejs.org"
fi
ok "Node.js v$NODE_VER"

# ── 2. Check Python ───────────────────────────────────────────────────────────
step "Checking Python"
PYTHON=""
for cmd in python3.12 python3.11 python3 python; do
  if command -v "$cmd" &>/dev/null; then
    VER=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
    MAJOR="${VER%%.*}"; MINOR="${VER##*.}"
    if [ "$MAJOR" -eq 3 ] && [ "$MINOR" -ge 11 ]; then
      PYTHON="$cmd"; break
    fi
  fi
done
if [ -z "$PYTHON" ]; then
  err "Python 3.11+ not found. Install from https://www.python.org/downloads/"
fi
ok "Python $($PYTHON --version)"

# ── 3. npm install ────────────────────────────────────────────────────────────
step "Installing npm packages"
cd "$PROJECT_ROOT"
npm install
ok "npm packages installed"

# ── 4. Python venv + deps ─────────────────────────────────────────────────────
step "Setting up Python virtual environment"
if [ ! -d "$BACKEND_DIR/.venv" ]; then
  echo "  Creating .venv…"
  "$PYTHON" -m venv "$BACKEND_DIR/.venv"
  ok ".venv created"
else
  ok ".venv already exists"
fi

source "$BACKEND_DIR/.venv/bin/activate"
echo "  Installing Python packages (this may take a minute)…"
pip install --upgrade pip --quiet
pip install -r "$BACKEND_DIR/requirements.txt" --quiet
ok "Python packages installed"

# ── 5. Download Playwright Chromium ──────────────────────────────────────────
step "Downloading Playwright Chromium (no system Chrome needed)"
PW_BROWSERS_DIR="$PROJECT_ROOT/resources/pw-browsers"
mkdir -p "$PW_BROWSERS_DIR"
if [ -z "$(ls -A "$PW_BROWSERS_DIR" 2>/dev/null)" ]; then
  echo "  Downloading Chromium (~170 MB, one-time)…"
  PLAYWRIGHT_BROWSERS_PATH="$PW_BROWSERS_DIR" playwright install chromium
  ok "Chromium downloaded to resources/pw-browsers/"
else
  ok "Chromium already present in resources/pw-browsers/"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   Setup complete!                       ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
echo ""
echo "  Start dev server:    npm run dev"
echo "  Build macOS DMG:     npm run dist:mac"
echo ""
