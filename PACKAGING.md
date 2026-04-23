# 打包发布指南

## 概述

本应用完全自包含，用户**无需安装 Python 或 Chrome**：
- **Python 后端** — 由 PyInstaller 编译为独立二进制文件
- **Chromium 浏览器** — 由 Playwright 下载后随应用一起打包
- **用户只需** 安装 DMG（macOS）或 EXE（Windows），填入 Gemini API Key 即可使用

---

## 一键开发环境搭建（首次克隆后运行）

### macOS
```bash
chmod +x scripts/setup_dev.sh
./scripts/setup_dev.sh
```

### Windows
```bat
scripts\setup_dev.bat
```

这两个脚本会自动完成：
1. 检查 Node.js（≥18）和 Python（≥3.11）是否已安装
2. 安装 npm 依赖（`npm install`）
3. 创建 Python 虚拟环境并安装所有 Python 包
4. 下载 Playwright Chromium 到 `resources/pw-browsers/`（约 170 MB，仅一次）

完成后运行 `npm run dev` 即可启动开发服务器。

---

## 打包安装包

### macOS（一条命令）
```bash
npm run dist:mac
```

> 包含：`build:backend`（PyInstaller + Chromium 下载）→ `build`（Vite 编译）→ `electron-builder`

### Windows（在 Windows 机器上运行）
```bat
npm run dist:win
```

### 手动分步执行（调试用）
```bash
# 1. 编译 Python 后端 + 下载 Playwright Chromium
npm run build:backend         # macOS
npm run build:backend:win     # Windows

# 2. 编译 Electron 前端
npm run build

# 3. 打包安装包
electron-builder --mac        # → release/*.dmg
electron-builder --win        # → release/*.exe
```

---

## 前提条件

| | macOS | Windows |
|---|---|---|
| Node.js | ≥ 18 | ≥ 18 |
| Python | ≥ 3.11 | ≥ 3.11 |
| Chrome | **不需要** | **不需要** |
| 网络（构建时）| 需要（下载 Chromium）| 需要（下载 Chromium）|
| 网络（运行时）| 需要（爬取航班数据）| 需要（爬取航班数据）|

---

## 用户使用说明（首次启动）

1. 安装应用后首次打开，左侧导航栏的 **设置** 图标会显示黄色提示点
2. 点击「设置」→ 在「Gemini API 密钥」栏填入自己的 API Key
3. 点击「保存」，密钥存储在本机，重启后无需重新输入
4. 即可使用全部功能

### 获取 Gemini API Key
1. 前往 https://aistudio.google.com/apikey
2. 用 Google 账号登录
3. 点击「Create API key」
4. 复制密钥，粘贴到设置页面

> 免费额度对日常使用完全够用。

---

## 打包后文件结构

```
release/
├── 航班价格分析工具-0.2.0.dmg          (macOS Intel 安装镜像)
├── 航班价格分析工具-0.2.0-arm64.dmg    (macOS Apple Silicon)
└── 航班价格分析工具 Setup 0.2.0.exe    (Windows 安装程序)

resources/                              (构建中间产物，不提交 git)
├── backend/                            (PyInstaller 编译的 Python 后端)
└── pw-browsers/                        (Playwright Chromium 浏览器)
```

---

## 注意事项

- **Chromium 已内置**：不依赖系统 Chrome，用户无需自行安装
- **Python 已内置**：PyInstaller 将 Python 解释器和所有依赖打包进二进制
- **数据目录**：爬取数据和报告存储在用户数据目录，卸载重装不会丢失
- **macOS 公证**：如需上传到 App Store 或通过 Gatekeeper，需要配置 Apple Developer 账号签名
- **resources/ 不提交 git**：build:backend 脚本会自动生成，加入 .gitignore
