#!/usr/bin/env bash
# 双击此文件即可开始构建 Mac 安装包 (.dmg)
# macOS 会自动用 Terminal 打开运行

cd "$(dirname "$0")"

# ── 颜色 ──────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'
BOLD='\033[1m'; NC='\033[0m'

clear
echo -e "${BLUE}${BOLD}"
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║     航班价格分析工具 — Mac 安装包构建工具      ║"
echo "  ╚══════════════════════════════════════════════╝"
echo -e "${NC}"
echo "  构建完成后会在 release/ 目录生成 .dmg 文件"
echo "  将 .dmg 发给使用者即可，无需其他任何依赖"
echo ""

# ── 检查 Node.js ──────────────────────────────────────────────────────────────
echo -e "${BOLD}[1/6] 检查 Node.js…${NC}"
if ! command -v node &>/dev/null; then
  echo -e "${RED}  ✗ 未找到 Node.js${NC}"
  echo "  请先安装 Node.js (v18+): https://nodejs.org"
  echo ""
  read -p "  按 Enter 打开下载页面…"
  open "https://nodejs.org"
  exit 1
fi
NODE_VER=$(node -e "process.stdout.write(process.versions.node)")
echo -e "${GREEN}  ✓ Node.js v$NODE_VER${NC}"

# ── 检查 Python ───────────────────────────────────────────────────────────────
echo -e "${BOLD}[2/6] 检查 Python…${NC}"
PYTHON=""
for cmd in python3.13 python3.12 python3.11 python3; do
  if command -v "$cmd" &>/dev/null; then
    VER=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
    MAJ="${VER%%.*}"; MIN="${VER##*.}"
    if [ "$MAJ" -eq 3 ] && [ "$MIN" -ge 11 ]; then
      PYTHON="$cmd"; break
    fi
  fi
done
if [ -z "$PYTHON" ]; then
  echo -e "${RED}  ✗ 未找到 Python 3.11+${NC}"
  echo "  请先安装: https://www.python.org/downloads/"
  read -p "  按 Enter 打开下载页面…"
  open "https://www.python.org/downloads/"
  exit 1
fi
echo -e "${GREEN}  ✓ $($PYTHON --version)${NC}"

# ── npm install ───────────────────────────────────────────────────────────────
echo -e "${BOLD}[3/6] 安装 npm 依赖…${NC}"
npm install --silent
echo -e "${GREEN}  ✓ npm 依赖就绪${NC}"

# ── Python venv ───────────────────────────────────────────────────────────────
echo -e "${BOLD}[4/6] 配置 Python 环境…${NC}"
if [ ! -d "backend/.venv" ]; then
  echo "  创建虚拟环境…"
  "$PYTHON" -m venv backend/.venv
fi
source backend/.venv/bin/activate
pip install --upgrade pip --quiet
pip install -r backend/requirements.txt --quiet
echo -e "${GREEN}  ✓ Python 环境就绪${NC}"

# ── 下载 Playwright Chromium ──────────────────────────────────────────────────
echo -e "${BOLD}[5/6] 准备内置浏览器 (Playwright Chromium)…${NC}"
mkdir -p resources/pw-browsers
if [ -z "$(ls -A resources/pw-browsers 2>/dev/null)" ]; then
  echo "  首次下载约 170 MB，请稍候…"
  PLAYWRIGHT_BROWSERS_PATH="$PWD/resources/pw-browsers" playwright install chromium
  echo -e "${GREEN}  ✓ 浏览器已下载${NC}"
else
  echo -e "${GREEN}  ✓ 浏览器已存在，跳过${NC}"
fi

# ── 构建 ──────────────────────────────────────────────────────────────────────
echo -e "${BOLD}[6/6] 编译并打包 .dmg…${NC}"
echo "  这一步需要几分钟，请耐心等待…"
echo ""

# Build Python backend with PyInstaller
bash scripts/build_backend.sh

# Build Electron frontend + package
npm run build
npx electron-builder --mac --config electron-builder.config.js

# ── 完成 ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}"
echo "  ╔══════════════════════════════════════╗"
echo "  ║   构建完成！                          ║"
echo "  ╚══════════════════════════════════════╝"
echo -e "${NC}"
echo "  .dmg 文件在：$(pwd)/release/"
echo ""
ls -lh release/*.dmg 2>/dev/null | awk '{print "  · "$NF" ("$5")"}'
echo ""
echo -e "  ${BOLD}现在可以将 .dmg 发给使用者了${NC}"
echo "  使用者只需：双击 .dmg → 拖入 Applications → 打开 App → 填入 API Key"
echo ""

# 自动打开 release 文件夹
open release/

read -p "  按 Enter 关闭此窗口…"
