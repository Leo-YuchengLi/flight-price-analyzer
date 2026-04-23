import { useState, useEffect } from 'react'
import { useBackend } from '../hooks/useBackend'

const S: Record<string, React.CSSProperties> = {
  page:    { padding: '32px 40px', maxWidth: 700, margin: '0 auto' },
  section: { background: '#1e293b', borderRadius: 12, padding: 28, marginBottom: 24,
             border: '1px solid #334155' },
  title:   { fontSize: 22, fontWeight: 600, color: '#f8fafc', marginBottom: 6 },
  sub:     { fontSize: 13, color: '#64748b', marginBottom: 24 },
  label:   { display: 'block', fontSize: 13, color: '#94a3b8', marginBottom: 6, fontWeight: 500 },
  input:   { width: '100%', background: '#0f172a', border: '1px solid #334155', borderRadius: 8,
             padding: '10px 12px', color: '#f8fafc', fontSize: 14, boxSizing: 'border-box',
             fontFamily: 'monospace', outline: 'none' },
  row:     { display: 'flex', gap: 10, marginTop: 16 },
  btnPrimary: { padding: '9px 20px', background: '#3b82f6', color: '#fff',
                border: 'none', borderRadius: 8, fontSize: 14, cursor: 'pointer', fontWeight: 500 },
  btnSecondary: { padding: '9px 20px', background: '#334155', color: '#e2e8f0',
                  border: 'none', borderRadius: 8, fontSize: 14, cursor: 'pointer' },
  badge:   { display: 'inline-flex', alignItems: 'center', gap: 6, padding: '4px 10px',
             borderRadius: 20, fontSize: 12, fontWeight: 500 },
  hint:    { fontSize: 12, color: '#475569', marginTop: 8, lineHeight: 1.5 },
  divider: { borderTop: '1px solid #1e293b', margin: '16px 0' },
}

export default function SettingsPage() {
  const { backendUrl } = useBackend()

  const [apiKey, setApiKey]       = useState('')
  const [saved, setSaved]         = useState(false)
  const [showKey, setShowKey]     = useState(false)
  const [keyStatus, setKeyStatus] = useState<{ configured: boolean; preview: string } | null>(null)
  const [saving, setSaving]       = useState(false)

  // Load persisted key and current backend status
  useEffect(() => {
    const load = async () => {
      const stored = await window.api.storeGet('gemini_api_key') as string | undefined
      if (stored) setApiKey(stored)
    }
    load()
  }, [])

  useEffect(() => {
    if (!backendUrl) return
    fetch(`${backendUrl}/api/settings/api-key/status`)
      .then(r => r.json())
      .then(setKeyStatus)
      .catch(() => {})
  }, [backendUrl])

  async function handleSave() {
    setSaving(true)
    setSaved(false)
    try {
      // 1. Persist to electron-store (survives restarts)
      await window.api.storeSet('gemini_api_key', apiKey.trim())
      // 2. Push to running backend immediately (no restart needed)
      if (backendUrl) {
        await fetch(`${backendUrl}/api/settings/api-key`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ api_key: apiKey.trim() }),
        })
        const status = await fetch(`${backendUrl}/api/settings/api-key/status`).then(r => r.json())
        setKeyStatus(status)
      }
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } finally {
      setSaving(false)
    }
  }

  function handleClear() {
    setApiKey('')
    window.api.storeSet('gemini_api_key', '')
    if (backendUrl) {
      fetch(`${backendUrl}/api/settings/api-key`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: '' }),
      })
    }
    setKeyStatus(null)
    setSaved(false)
  }

  const maskedDisplay = apiKey ? (showKey ? apiKey : '•'.repeat(Math.min(apiKey.length, 40))) : ''

  return (
    <div style={S.page}>
      <div style={{ marginBottom: 32 }}>
        <div style={S.title}>设置</div>
        <div style={S.sub}>管理 API 密钥和应用配置</div>
      </div>

      {/* ── API Key section ── */}
      <div style={S.section}>
        <div style={{ fontSize: 16, fontWeight: 600, color: '#e2e8f0', marginBottom: 4 }}>
          Gemini API 密钥
        </div>
        <div style={{ fontSize: 13, color: '#64748b', marginBottom: 20 }}>
          用于 AI 报告分析功能。请前往{' '}
          <a
            href="https://aistudio.google.com/apikey"
            style={{ color: '#60a5fa', textDecoration: 'none' }}
            onClick={e => { e.preventDefault(); window.open('https://aistudio.google.com/apikey') }}
          >
            Google AI Studio
          </a>{' '}
          获取免费 API Key（需要 Google 账号）。
        </div>

        {/* Current status badge */}
        {keyStatus && (
          <div style={{ marginBottom: 16 }}>
            <span style={{
              ...S.badge,
              background: keyStatus.configured ? '#052e16' : '#2d1515',
              color: keyStatus.configured ? '#4ade80' : '#f87171',
              border: `1px solid ${keyStatus.configured ? '#166534' : '#7f1d1d'}`,
            }}>
              <span style={{ fontSize: 10 }}>{keyStatus.configured ? '●' : '○'}</span>
              {keyStatus.configured ? `已配置 ${keyStatus.preview}` : '未配置'}
            </span>
          </div>
        )}

        <label style={S.label}>API Key</label>
        <div style={{ position: 'relative' }}>
          <input
            type={showKey ? 'text' : 'password'}
            value={apiKey}
            onChange={e => setApiKey(e.target.value)}
            placeholder="AIzaSy…"
            style={{ ...S.input, paddingRight: 80 }}
            onKeyDown={e => e.key === 'Enter' && handleSave()}
          />
          <button
            onClick={() => setShowKey(v => !v)}
            style={{
              position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)',
              background: 'none', border: 'none', color: '#64748b', cursor: 'pointer',
              fontSize: 12, padding: '2px 6px',
            }}
          >
            {showKey ? '隐藏' : '显示'}
          </button>
        </div>

        <div style={S.hint}>
          密钥保存在本机，不会上传至任何服务器。每次启动应用时自动加载。
        </div>

        <div style={S.row}>
          <button
            onClick={handleSave}
            disabled={saving || !apiKey.trim()}
            style={{ ...S.btnPrimary, opacity: saving || !apiKey.trim() ? 0.5 : 1 }}
          >
            {saving ? '保存中…' : saved ? '✓ 已保存' : '保存'}
          </button>
          {apiKey && (
            <button onClick={handleClear} style={{ ...S.btnSecondary, color: '#f87171' }}>
              清除
            </button>
          )}
        </div>
      </div>

      {/* ── About section ── */}
      <div style={S.section}>
        <div style={{ fontSize: 16, fontWeight: 600, color: '#e2e8f0', marginBottom: 16 }}>
          关于
        </div>
        <div style={{ display: 'grid', gap: 8 }}>
          {[
            ['应用名称', '航班价格分析工具'],
            ['版本', 'v0.2.0'],
            ['AI 模型', 'Gemini 2.5 Flash'],
            ['数据来源', 'hk.trip.com'],
          ].map(([k, v]) => (
            <div key={k} style={{ display: 'flex', justifyContent: 'space-between',
                                   padding: '8px 0', borderBottom: '1px solid #1e293b' }}>
              <span style={{ color: '#64748b', fontSize: 13 }}>{k}</span>
              <span style={{ color: '#e2e8f0', fontSize: 13 }}>{v}</span>
            </div>
          ))}
        </div>

        <div style={{ marginTop: 16, fontSize: 12, color: '#475569', lineHeight: 1.7 }}>
          本工具仅供内部数据分析使用。搜索功能需要本机安装 Google Chrome 浏览器。
        </div>
      </div>

      {/* ── Usage guide ── */}
      <div style={S.section}>
        <div style={{ fontSize: 16, fontWeight: 600, color: '#e2e8f0', marginBottom: 16 }}>
          使用说明
        </div>
        <div style={{ display: 'grid', gap: 12 }}>
          {[
            ['1. 获取 API Key', '前往 Google AI Studio (aistudio.google.com) → 左侧"Get API key" → 创建密钥，免费额度足够日常使用。'],
            ['2. 输入并保存', '将密钥粘贴到上方输入框，点击"保存"。密钥存储在本机，重启应用后无需重新输入。'],
            ['3. 开始使用', '进入"搜索 & 抓取"添加航线并批量搜索，完成后在"分析报告"页面选择数据生成 AI 分析报告。'],
            ['4. 搜索要求', '爬取功能需要本机已安装 Google Chrome 浏览器（会自动调用）。'],
          ].map(([title, desc]) => (
            <div key={title} style={{ padding: '12px 14px', background: '#0f172a',
                                       borderRadius: 8, border: '1px solid #1e293b' }}>
              <div style={{ fontSize: 13, color: '#60a5fa', fontWeight: 500, marginBottom: 4 }}>
                {title}
              </div>
              <div style={{ fontSize: 13, color: '#94a3b8', lineHeight: 1.6 }}>{desc}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
