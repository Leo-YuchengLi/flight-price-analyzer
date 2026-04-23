import { useState, useRef, useEffect, useCallback } from 'react'
import { useBackend } from '../hooks/useBackend'
import ConfirmationCard, { SearchIntent } from '../components/ConfirmationCard'

// ── Types ─────────────────────────────────────────────────────────────────────

type MessageType = 'text' | 'confirmation' | 'thinking'

interface Message {
  id: string
  role: 'user' | 'assistant'
  type: MessageType
  content?: string
  intent?: SearchIntent
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const uid = () => Math.random().toString(36).slice(2, 9)

const WELCOME: Message = {
  id: 'welcome',
  role: 'assistant',
  type: 'text',
  content: `你好！我是你的航班比价助手。告诉我你的需求，我来规划搜索任务。

我支持两种模式：
• **批量比价** — 多条航线 × 多个日期的对比矩阵报告（适合航司商务分析）
• **单线详查** — 某条航线按日期/每周某天的价格序列

你可以这样说：
• 「今夏 LON 飞主要中国城市，经济舱和商务舱每月比价」
• 「LON→BJS 6月每周五的经济舱价格」
• 「夏季每周一 LON→BJS 价格趋势」`,
}

// ── Chat components ───────────────────────────────────────────────────────────

function UserBubble({ content }: { content: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 14 }}>
      <div style={{
        background: 'linear-gradient(135deg,#2563eb,#4f46e5)',
        color: 'white', padding: '10px 15px',
        borderRadius: '16px 16px 4px 16px',
        maxWidth: '72%', fontSize: 14, lineHeight: 1.65,
        whiteSpace: 'pre-wrap',
      }}>
        {content}
      </div>
    </div>
  )
}

function AssistantBubble({ content }: { content: string }) {
  // Parse simple markdown: **bold**, bullet lines
  const lines = content.split('\n')
  return (
    <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: 14 }}>
      <div style={{ display: 'flex', gap: 9, alignItems: 'flex-start', maxWidth: '82%' }}>
        <div style={{
          width: 30, height: 30, borderRadius: '50%',
          background: 'linear-gradient(135deg,#1e3a8a,#312e81)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 15, flexShrink: 0, marginTop: 2,
        }}>✈</div>
        <div style={{
          background: '#1e293b', color: '#e2e8f0',
          padding: '11px 15px', borderRadius: '4px 16px 16px 16px',
          fontSize: 14, lineHeight: 1.65,
        }}>
          {lines.map((line, i) => {
            const isBold = line.startsWith('**') && line.endsWith('**')
            const isBullet = line.startsWith('•') || line.startsWith('·')
            const text = line.replace(/\*\*(.*?)\*\*/g, '$1')
            if (!line.trim()) return <div key={i} style={{ height: 6 }} />
            return (
              <div key={i} style={{
                fontWeight: isBold ? 600 : 400,
                color: isBold ? '#93c5fd' : isBullet ? '#cbd5e1' : '#e2e8f0',
                marginLeft: isBullet ? 4 : 0,
                marginBottom: 2,
              }}>
                {text}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

function ThinkingBubble() {
  return (
    <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: 14 }}>
      <div style={{ display: 'flex', gap: 9, alignItems: 'center' }}>
        <div style={{
          width: 30, height: 30, borderRadius: '50%',
          background: 'linear-gradient(135deg,#1e3a8a,#312e81)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 15,
        }}>✈</div>
        <div style={{
          background: '#1e293b', padding: '11px 16px',
          borderRadius: '4px 16px 16px 16px',
          display: 'flex', gap: 5, alignItems: 'center',
        }}>
          <span style={{ color: '#475569', fontSize: 12 }}>分析中</span>
          {[0, 0.2, 0.4].map((delay, i) => (
            <div key={i} style={{
              width: 5, height: 5, borderRadius: '50%',
              background: '#3b82f6',
              animation: `bounce 0.9s ${delay}s infinite`,
            }} />
          ))}
          <style>{`@keyframes bounce{0%,80%,100%{transform:translateY(0)}40%{transform:translateY(-5px)}}`}</style>
        </div>
      </div>
    </div>
  )
}

// ── Settings drawer ───────────────────────────────────────────────────────────

function ApiKeyDrawer({ onClose }: { onClose: () => void }) {
  const [key, setKey] = useState(() => localStorage.getItem('gemini_api_key') || '')
  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100,
    }} onClick={onClose}>
      <div style={{
        background: '#1e293b', border: '1px solid #334155',
        borderRadius: 12, padding: '24px 28px', width: 420,
      }} onClick={e => e.stopPropagation()}>
        <h3 style={{ margin: '0 0 12px', fontSize: 15, color: '#f8fafc' }}>⚙️ Gemini API Key</h3>
        <p style={{ margin: '0 0 12px', fontSize: 12, color: '#64748b' }}>
          输入你的 Google Gemini API Key（留空则使用后端默认 Key）
        </p>
        <input
          style={{
            width: '100%', background: '#0f172a', border: '1px solid #334155',
            borderRadius: 6, padding: '8px 12px', color: '#e2e8f0', fontSize: 13,
            boxSizing: 'border-box', marginBottom: 14,
          }}
          type="password" placeholder="AIzaSy..." value={key}
          onChange={e => setKey(e.target.value)}
        />
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button style={{ padding: '7px 16px', background: 'transparent', color: '#64748b', border: '1px solid #334155', borderRadius: 6, cursor: 'pointer', fontSize: 13 }} onClick={onClose}>取消</button>
          <button
            style={{ padding: '7px 16px', background: 'linear-gradient(135deg,#2563eb,#4f46e5)', color: 'white', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 13 }}
            onClick={() => { localStorage.setItem('gemini_api_key', key); onClose() }}
          >保存</button>
        </div>
      </div>
    </div>
  )
}

// ── Suggestion chips ──────────────────────────────────────────────────────────

const SUGGESTIONS = [
  '今夏 LON 飞主要中国城市批量比价（每月代表日）',
  'LON→BJS 6月每周五的价格，经济舱',
  'LON→BJS/CTU/PVG/CAN，Q3 按月比价',
  'LON→BJS 夏季每周的价格趋势',
]

// ── Main page ─────────────────────────────────────────────────────────────────

const STORAGE_MSGS = 'chat_messages_v1'
const STORAGE_HIST = 'chat_history_v1'

function loadMessages(): Message[] {
  try {
    const raw = localStorage.getItem(STORAGE_MSGS)
    if (raw) {
      const msgs = JSON.parse(raw) as Message[]
      return msgs.filter(m => m.type !== 'thinking')  // strip transient states
    }
  } catch { /* ignore */ }
  return [WELCOME]
}

function loadHistory(): { role: string; content: string }[] {
  try {
    const raw = localStorage.getItem(STORAGE_HIST)
    if (raw) return JSON.parse(raw)
  } catch { /* ignore */ }
  return []
}

export default function ChatSearchPage() {
  const { url: backendUrl, status } = useBackend()
  const [messages, setMessages] = useState<Message[]>(loadMessages)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [showSuggestions, setShowSuggestions] = useState(() => {
    // Show suggestions only if it's a fresh session (only welcome message)
    const saved = localStorage.getItem(STORAGE_MSGS)
    if (!saved) return true
    try { return JSON.parse(saved).filter((m: Message) => m.type !== 'thinking').length <= 1 }
    catch { return true }
  })
  const msgAreaRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const historyRef = useRef<{ role: string; content: string }[]>(loadHistory())

  // Persist messages to localStorage whenever they change
  useEffect(() => {
    const toSave = messages.filter(m => m.type !== 'thinking')
    localStorage.setItem(STORAGE_MSGS, JSON.stringify(toSave))
  }, [messages])

  useEffect(() => {
    const el = msgAreaRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, loading])

  const sendMessage = useCallback(async (text?: string) => {
    const msg = (text ?? input).trim()
    if (!msg || loading || !backendUrl || status !== 'connected') return

    setInput('')
    setLoading(true)
    setShowSuggestions(false)

    const userMsg: Message = { id: uid(), role: 'user', type: 'text', content: msg }
    setMessages(prev => [...prev, userMsg])

    try {
      const apiKey = localStorage.getItem('gemini_api_key') || undefined
      const res = await fetch(`${backendUrl}/api/chat/message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ history: historyRef.current, message: msg, api_key: apiKey || null }),
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(err.detail || `HTTP ${res.status}`)
      }

      const data = await res.json()
      const intent: SearchIntent = data.intent
      const displayMsg: string = data.display_message

      historyRef.current = [
        ...historyRef.current,
        { role: 'user', content: msg },
        { role: 'assistant', content: displayMsg },
      ]
      localStorage.setItem(STORAGE_HIST, JSON.stringify(historyRef.current))

      if (data.ready) {
        setMessages(prev => [
          ...prev,
          { id: uid(), role: 'assistant', type: 'text', content: displayMsg },
          { id: uid(), role: 'assistant', type: 'confirmation', intent },
        ])
      } else {
        setMessages(prev => [
          ...prev,
          { id: uid(), role: 'assistant', type: 'text', content: displayMsg },
        ])
      }
    } catch (err: any) {
      const msg = String(err.message || err)
      const isKeyError = /api.key|invalid|401|403|permission|authenticate/i.test(msg)
      if (isKeyError) {
        alert('⚠️ Gemini API Key 无效或未配置\n\n请前往左侧「设置」页面填入正确的 API Key 后重试。')
      }
      setMessages(prev => [
        ...prev,
        {
          id: uid(), role: 'assistant', type: 'text',
          content: isKeyError
            ? '⚠️ API Key 无效，请到左侧「设置」页面更新后重试。'
            : `⚠️ 请求失败：${msg}`,
        },
      ])
    }

    setLoading(false)
    inputRef.current?.focus()
  }, [input, loading, backendUrl, status])

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() }
  }

  function handleNewChat() {
    setMessages([WELCOME])
    historyRef.current = []
    localStorage.removeItem(STORAGE_MSGS)
    localStorage.removeItem(STORAGE_HIST)
    setInput('')
    setShowSuggestions(true)
    inputRef.current?.focus()
  }

  function handleAdjust() {
    setMessages(prev => prev.filter(m => m.type !== 'confirmation'))
    inputRef.current?.focus()
  }

  const S = styles

  return (
    <div style={S.page}>
      {showSettings && <ApiKeyDrawer onClose={() => setShowSettings(false)} />}

      {/* Header */}
      <div style={S.header}>
        <div style={S.agentAvatar}>✈</div>
        <div>
          <h1 style={S.title}>AI 比价助手</h1>
          <p style={S.subtitle}>描述你的需求，自动配置批量比价任务</p>
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
          <button style={S.iconBtn} onClick={handleNewChat} title="新对话">🔄</button>
          <button style={S.iconBtn} onClick={() => setShowSettings(true)} title="设置API Key">⚙️</button>
          <span style={{
            background: status === 'connected' ? '#14532d' : '#7f1d1d',
            color: status === 'connected' ? '#4ade80' : '#f87171',
            padding: '3px 10px', borderRadius: 20, fontSize: 12,
          }}>
            {status === 'connected' ? '已连接' : '未连接'}
          </span>
        </div>
      </div>

      {/* Messages */}
      <div ref={msgAreaRef} style={S.msgArea}>
        {messages.map(msg => {
          if (msg.role === 'user') return <UserBubble key={msg.id} content={msg.content!} />
          if (msg.type === 'confirmation' && msg.intent) {
            return (
              <div key={msg.id} style={{ marginBottom: 14, paddingLeft: 39 }}>
                <ConfirmationCard intent={msg.intent} onAdjust={handleAdjust} />
              </div>
            )
          }
          return <AssistantBubble key={msg.id} content={msg.content!} />
        })}

        {loading && <ThinkingBubble />}

        {/* Suggestion chips — only shown before first user message */}
        {showSuggestions && !loading && (
          <div style={{ paddingLeft: 39, marginTop: 8 }}>
            <div style={{ fontSize: 12, color: '#475569', marginBottom: 8 }}>快速开始：</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {SUGGESTIONS.map(s => (
                <button key={s} style={S.suggestionChip} onClick={() => sendMessage(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

      </div>

      {/* Input */}
      <div style={S.inputArea}>
        <div style={S.inputWrap}>
          <textarea
            ref={inputRef}
            style={S.textarea}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              status !== 'connected'
                ? '等待后端连接…'
                : '描述你的比价需求，如：伦敦飞主要中国城市今夏价格对比…'
            }
            disabled={loading || status !== 'connected'}
            rows={1}
          />
          <button
            style={{ ...S.sendBtn, opacity: (!input.trim() || loading || status !== 'connected') ? 0.35 : 1 }}
            disabled={!input.trim() || loading || status !== 'connected'}
            onClick={() => sendMessage()}
          >
            ↑
          </button>
        </div>
        <p style={{ margin: '5px 0 0', fontSize: 11, color: '#334155', textAlign: 'center' }}>
          由 Gemini AI 解析 · Enter 发送 · Shift+Enter 换行
        </p>
      </div>
    </div>
  )
}

// ── Styles ────────────────────────────────────────────────────────────────────

const styles = {
  page: {
    height: '100%', display: 'flex', flexDirection: 'column',
    background: '#0f172a',
    fontFamily: '"PingFang SC","Microsoft YaHei",system-ui,sans-serif',
    color: '#e2e8f0',
  } as React.CSSProperties,
  header: {
    background: '#1e293b', borderBottom: '1px solid #334155',
    padding: '12px 24px', display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0,
  } as React.CSSProperties,
  agentAvatar: {
    width: 34, height: 34, borderRadius: '50%',
    background: 'linear-gradient(135deg,#1e3a8a,#312e81)',
    display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16, flexShrink: 0,
  } as React.CSSProperties,
  title: { margin: 0, fontSize: 15, fontWeight: 500, color: '#f8fafc' } as React.CSSProperties,
  subtitle: { margin: '1px 0 0', fontSize: 11, color: '#64748b' } as React.CSSProperties,
  iconBtn: {
    background: 'none', border: 'none', cursor: 'pointer',
    fontSize: 16, padding: '4px 6px', borderRadius: 6, color: '#64748b',
  } as React.CSSProperties,
  msgArea: { flex: 1, overflow: 'auto', padding: '24px 28px' } as React.CSSProperties,
  inputArea: {
    padding: '14px 28px 18px', borderTop: '1px solid #1e293b',
    background: '#0f172a', flexShrink: 0,
  } as React.CSSProperties,
  inputWrap: {
    display: 'flex', gap: 8, background: '#1e293b',
    border: '1px solid #334155', borderRadius: 12,
    padding: '8px 8px 8px 14px', alignItems: 'flex-end',
  } as React.CSSProperties,
  textarea: {
    flex: 1, background: 'none', border: 'none', outline: 'none',
    color: '#e2e8f0', fontSize: 14, lineHeight: 1.6,
    resize: 'none', maxHeight: 120, fontFamily: 'inherit',
  } as React.CSSProperties,
  sendBtn: {
    width: 34, height: 34, background: 'linear-gradient(135deg,#2563eb,#4f46e5)',
    border: 'none', borderRadius: 8, color: 'white', fontSize: 18, fontWeight: 700,
    cursor: 'pointer', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
  } as React.CSSProperties,
  suggestionChip: {
    background: '#0f2040', border: '1px solid #1e4080',
    color: '#93c5fd', borderRadius: 20, padding: '5px 12px',
    fontSize: 12, cursor: 'pointer', textAlign: 'left' as const,
    transition: 'background 0.15s',
  } as React.CSSProperties,
}
