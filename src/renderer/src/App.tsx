import { HashRouter, Routes, Route, NavLink } from 'react-router-dom'
import { useEffect, useState } from 'react'
import ChatSearchPage from './pages/ChatSearchPage'
import ClassicSearchPage from './pages/ClassicSearchPage'
import ReportsPage from './pages/ReportsPage'
import AnalysisPage from './pages/AnalysisPage'
import SettingsPage from './pages/SettingsPage'
import { useBackend } from './hooks/useBackend'

// ── Minimal SVG icons (16×16, stroke-based, no fill) ─────────────────────────

const IconChat = () => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" style={{ flexShrink: 0 }}>
    <path d="M1 2.5C1 1.67 1.67 1 2.5 1h10c.83 0 1.5.67 1.5 1.5v7c0 .83-.67 1.5-1.5 1.5H8.5L5 14v-3H2.5C1.67 11 1 10.33 1 9.5v-7z"
      stroke="currentColor" strokeWidth="1.1" strokeLinejoin="round"/>
  </svg>
)

const IconSearch = () => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" style={{ flexShrink: 0 }}>
    <circle cx="6.5" cy="6.5" r="4.5" stroke="currentColor" strokeWidth="1.1"/>
    <path d="M10.5 10.5L14 14" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round"/>
  </svg>
)

const IconDatabase = () => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" style={{ flexShrink: 0 }}>
    <ellipse cx="7.5" cy="3.5" rx="5" ry="2" stroke="currentColor" strokeWidth="1.1"/>
    <path d="M2.5 3.5v4c0 1.1 2.24 2 5 2s5-.9 5-2v-4" stroke="currentColor" strokeWidth="1.1"/>
    <path d="M2.5 7.5v4c0 1.1 2.24 2 5 2s5-.9 5-2v-4" stroke="currentColor" strokeWidth="1.1"/>
  </svg>
)

const IconTrend = () => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" style={{ flexShrink: 0 }}>
    <polyline points="1,11 5,6.5 8.5,9.5 14,3" stroke="currentColor" strokeWidth="1.1"
      strokeLinecap="round" strokeLinejoin="round"/>
    <polyline points="10,3 14,3 14,7" stroke="currentColor" strokeWidth="1.1"
      strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
)

const IconSliders = () => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" style={{ flexShrink: 0 }}>
    <line x1="1" y1="4" x2="14" y2="4" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round"/>
    <line x1="1" y1="7.5" x2="14" y2="7.5" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round"/>
    <line x1="1" y1="11" x2="14" y2="11" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round"/>
    <circle cx="4.5" cy="4" r="1.5" fill="#0a0c12" stroke="currentColor" strokeWidth="1.1"/>
    <circle cx="10" cy="7.5" r="1.5" fill="#0a0c12" stroke="currentColor" strokeWidth="1.1"/>
    <circle cx="6" cy="11" r="1.5" fill="#0a0c12" stroke="currentColor" strokeWidth="1.1"/>
  </svg>
)

const IconPlane = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style={{ flexShrink: 0 }}>
    <path d="M14 7.5L9 4V1.5a1 1 0 00-2 0V4L2 7.5v1.5l5-1.5V11l-2 1v1l3-1 3 1v-1l-2-1V7.5l5 1.5V7.5z"
      fill="currentColor" opacity="0.9"/>
  </svg>
)

// ── Sidebar ───────────────────────────────────────────────────────────────────

const NAV_ITEMS = [
  { to: '/',        end: true,  icon: <IconChat />,     label: 'AI 对话规划' },
  { to: '/classic', end: false, icon: <IconSearch />,   label: '搜索 & 抓取' },
  { to: '/reports', end: false, icon: <IconDatabase />, label: '历史数据库' },
  { to: '/analysis',end: false, icon: <IconTrend />,    label: '分析报告'   },
]

function Sidebar() {
  const { status, backendUrl } = useBackend()
  const [hasApiKey, setHasApiKey] = useState<boolean | null>(null)

  useEffect(() => {
    const check = async () => {
      try {
        const stored = await window.api?.storeGet('gemini_api_key') as string | undefined
        setHasApiKey(Boolean(stored?.trim()))
      } catch { setHasApiKey(false) }
    }
    check()
  }, [backendUrl])

  const drag = { WebkitAppRegion: 'drag' as unknown as undefined }
  const noDrag = { WebkitAppRegion: 'no-drag' as unknown as undefined }

  const linkStyle = ({ isActive }: { isActive: boolean }): React.CSSProperties => ({
    display: 'flex', alignItems: 'center', gap: 9,
    padding: '8px 12px 8px 14px',
    borderRadius: 6,
    textDecoration: 'none',
    fontSize: 13,
    fontWeight: isActive ? 500 : 400,
    letterSpacing: '0.01em',
    color: isActive ? '#e2e8f0' : '#52596b',
    background: isActive ? '#13182a' : 'transparent',
    borderLeft: isActive ? '2px solid #3b7ff5' : '2px solid transparent',
    transition: 'color 0.12s, background 0.12s, border-color 0.12s',
    ...noDrag,
  })

  return (
    <nav style={{
      width: 210, minHeight: '100vh',
      background: '#0a0c12',
      borderRight: '1px solid #161b27',
      padding: '0 10px 16px',
      display: 'flex', flexDirection: 'column',
      flexShrink: 0,
    }}>

      {/* ── Drag handle / Logo ── */}
      <div style={{
        ...drag,
        padding: '28px 12px 14px',
        marginBottom: 4,
        borderBottom: '1px solid #161b27',
        userSelect: 'none',
        cursor: 'default',
      }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 8, ...noDrag }}>
          <span style={{ color: '#3b7ff5', display: 'flex', alignItems: 'center' }}>
            <IconPlane />
          </span>
          <span style={{ fontSize: 13, fontWeight: 600, color: '#d1d8e8', letterSpacing: '0.02em' }}>
            航班分析工具
          </span>
        </span>
      </div>

      {/* ── Nav items ── */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 1, marginTop: 8 }}>
        {NAV_ITEMS.map(item => (
          <NavLink key={item.to} to={item.to} end={item.end} style={linkStyle}>
            {item.icon}
            {item.label}
          </NavLink>
        ))}
      </div>

      {/* ── Settings (pinned to bottom) ── */}
      <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: 1 }}>
        <div style={{ borderTop: '1px solid #161b27', marginBottom: 8 }} />

        <NavLink to="/settings" style={({ isActive }) => ({
          ...linkStyle({ isActive }),
          position: 'relative',
        })}>
          <IconSliders />
          <span>设置</span>
          {hasApiKey === false && (
            <span style={{
              marginLeft: 'auto',
              width: 5, height: 5, borderRadius: '50%',
              background: '#f59e0b', flexShrink: 0,
            }}/>
          )}
        </NavLink>

        {/* Status */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6,
          padding: '6px 14px', marginTop: 4,
        }}>
          <span style={{
            width: 5, height: 5, borderRadius: '50%', flexShrink: 0,
            background: status === 'connected' ? '#34c97a'
                       : status === 'connecting' ? '#f59e0b' : '#f06060',
            boxShadow: status === 'connected' ? '0 0 5px #34c97a66' : 'none',
          }}/>
          <span style={{ fontSize: 11, color: '#353d4e', letterSpacing: '0.02em' }}>
            {status === 'connected' ? '后端就绪'
           : status === 'connecting' ? '连接中…' : '后端离线'}
          </span>
        </div>
      </div>
    </nav>
  )
}

// ── App ───────────────────────────────────────────────────────────────────────

// Wrapper for pages that need their own independent scroll (not ChatSearchPage,
// which manages scrolling internally via its msgArea flex child).
function ScrollPage({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ height: '100%', overflowY: 'auto' }}>
      {children}
    </div>
  )
}

export default function App() {
  return (
    <HashRouter>
      {/*
        Root: exactly viewport height, no outer scroll.
        Each page manages its own scroll — prevents the "scrolled past header"
        bug where auto-scrolling messages would push the top bar out of view.
      */}
      <div style={{ display: 'flex', height: '100vh', overflow: 'hidden', background: '#0d1117' }}>
        <Sidebar />
        <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <Routes>
            {/* Fixed-layout pages: manage their own internal scroll, no outer scroll wrapper */}
            <Route path="/"         element={<ChatSearchPage />} />
            <Route path="/reports"  element={<ReportsPage />} />
            <Route path="/analysis" element={<AnalysisPage />} />
            {/* Long-form pages: need outer scroll so content below the fold is reachable */}
            <Route path="/classic"  element={<ScrollPage><ClassicSearchPage /></ScrollPage>} />
            <Route path="/settings" element={<ScrollPage><SettingsPage /></ScrollPage>} />
          </Routes>
        </div>
      </div>
    </HashRouter>
  )
}
