/**
 * electron-builder configuration
 * Build: npm run dist:mac  /  npm run dist:win  /  npm run dist:all
 *
 * Prerequisites:
 *   1. Build the Python backend with PyInstaller first:
 *        npm run build:backend        (macOS)
 *        npm run build:backend:win    (Windows)
 *   2. Then run the Electron build:
 *        npm run dist:mac / dist:win
 */

/** @type {import('electron-builder').Configuration} */
module.exports = {
  appId: 'com.flightanalyzer.app',
  productName: '航班价格分析工具',

  // Output directory for installers/DMGs
  directories: {
    output: 'release',
  },

  // Electron source files (compiled by electron-vite)
  files: [
    'out/**/*',
    'node_modules/**/*',
    '!node_modules/.cache',
  ],

  // Bundle the compiled Python backend + Playwright Chromium into app resources.
  // pythonBridge.ts resolves:
  //   process.resourcesPath + '/backend/backend(.exe)'   — Python backend
  //   process.resourcesPath + '/pw-browsers/'            — Playwright Chromium
  extraResources: [
    {
      from: 'resources/backend/',
      to: 'backend/',
      filter: ['**/*'],
    },
    {
      from: 'resources/pw-browsers/',
      to: 'pw-browsers/',
      filter: ['**/*'],
    },
  ],

  // ── macOS ──────────────────────────────────────────────────────────────────
  mac: {
    target: [
      { target: 'dmg', arch: ['x64', 'arm64'] },
      { target: 'zip', arch: ['x64', 'arm64'] },
    ],
    category: 'public.app-category.productivity',
    icon: 'resources/icon.icns',
  },
  dmg: {
    title: '${productName} ${version}',
    contents: [
      { x: 410, y: 150, type: 'link', path: '/Applications' },
      { x: 130, y: 150, type: 'file' },
    ],
  },

  // ── Windows ────────────────────────────────────────────────────────────────
  win: {
    target: [
      { target: 'nsis', arch: ['x64'] },
    ],
    icon: 'resources/icon.ico',
  },
  nsis: {
    oneClick: false,
    allowToChangeInstallationDirectory: true,
    createDesktopShortcut: true,
    createStartMenuShortcut: true,
    shortcutName: '航班分析工具',
    installerIcon: 'resources/icon.ico',
    uninstallerIcon: 'resources/icon.ico',
  },

  // ── Linux (optional) ───────────────────────────────────────────────────────
  linux: {
    target: [{ target: 'AppImage', arch: ['x64'] }],
    category: 'Utility',
  },
}
