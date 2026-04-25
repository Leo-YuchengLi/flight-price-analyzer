import { useState, useEffect, useRef, useCallback } from 'react'
import { useBackend } from '../hooks/useBackend'

// ── Types ─────────────────────────────────────────────────────────────────────

interface ReportMeta {
  report_id: string
  title: string
  created_at: string
  total_flights: number
  has_flights?: boolean
  stats: { currency: string; date_range: string; total_flights: number }
}

interface AnalysisMeta {
  analysis_id: string
  title: string
  created_at: string
  outline: string
}

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

type CreationStep = 'select' | 'outline' | 'generating' | 'done'

const SUGGESTED_QUESTIONS = [
  '哪条航线国航溢价最高？原因分析',
  '国航在哪些时段价格竞争力最强？',
  '针对高溢价航线，有什么调价建议？',
  '哪些航线国航缺少报价？',
  '与竞争对手相比国航整体表现如何？',
]

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function AnalysisPage() {
  const { url: backendUrl, status } = useBackend()

  // Sidebar list
  const [analyses, setAnalyses]       = useState<AnalysisMeta[]>([])
  const [loadingList, setLoadingList]  = useState(false)

  // Active analysis
  const [activeId, setActiveId]         = useState<string | null>(null)
  const [activeTitle, setActiveTitle]   = useState('')
  const [loadingActive, setLoadingActive] = useState(false)
  const [iframeSrc, setIframeSrc]       = useState('')
  const prevBlobUrl = useRef('')

  // Chat
  const [chatHistory, setChatHistory]     = useState<ChatMessage[]>([])
  const [chatInput, setChatInput]         = useState('')
  const [chatStreaming, setChatStreaming]  = useState(false)
  const chatBottomRef = useRef<HTMLDivElement>(null)
  const apiKey = localStorage.getItem('gemini_api_key') || ''

  // Creation modal
  const [showModal, setShowModal]         = useState(false)
  const [step, setStep]                   = useState<CreationStep>('select')
  const [reports, setReports]             = useState<ReportMeta[]>([])
  const [selectedIds, setSelectedIds]     = useState<string[]>([])
  const [modalTitle, setModalTitle]       = useState('')
  const [modalApiKey, setModalApiKey]     = useState(() => localStorage.getItem('gemini_api_key') || '')
  const [outline, setOutline]             = useState('')
  const [editedOutline, setEditedOutline] = useState('')
  const [generatingOutline, setGeneratingOutline] = useState(false)
  const [genStatus, setGenStatus]         = useState('')

  // Cache merged flights between outline and generate steps (avoids double fetch)
  const mergedFlightsCache = useRef<{ flights: object[]; date_ranges: object[] } | null>(null)

  // Use a ref to accumulate streamed HTML (avoids stale-closure bug)
  const streamedHtmlRef = useRef('')
  const [streamedHtmlDisplay, setStreamedHtmlDisplay] = useState('')

  // ── Fetch analyses list ─────────────────────────────────────────────────────

  const fetchAnalyses = useCallback(async () => {
    if (!backendUrl || status !== 'connected') return
    setLoadingList(true)
    try {
      const res = await fetch(`${backendUrl}/api/analysis/list`)
      setAnalyses(await res.json())
    } catch { /* ignore */ }
    setLoadingList(false)
  }, [backendUrl, status])

  useEffect(() => { fetchAnalyses() }, [fetchAnalyses])

  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chatHistory, chatStreaming])

  // ── Load analysis ───────────────────────────────────────────────────────────

  async function loadAnalysis(id: string, title: string) {
    if (activeId === id) return
    setActiveId(id)
    setActiveTitle(title)
    setIframeSrc('')
    setChatHistory([])
    setLoadingActive(true)
    try {
      // Fetch full HTML and create a blob URL to avoid Electron cross-origin restrictions
      const res = await fetch(`${backendUrl}/api/analysis/${id}/html`)
      const html = await res.text()
      if (prevBlobUrl.current) URL.revokeObjectURL(prevBlobUrl.current)
      const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
      const blobUrl = URL.createObjectURL(blob)
      prevBlobUrl.current = blobUrl
      setIframeSrc(blobUrl)
    } catch { /* ignore */ }
    setLoadingActive(false)
  }

  // ── Delete analysis ─────────────────────────────────────────────────────────

  async function deleteAnalysis(id: string, e: React.MouseEvent) {
    e.stopPropagation()
    if (!confirm('确认删除此分析报告？')) return
    await fetch(`${backendUrl}/api/analysis/${id}`, { method: 'DELETE' })
    setAnalyses(a => a.filter(x => x.analysis_id !== id))
    if (activeId === id) { setActiveId(null); setIframeSrc(''); setChatHistory([]) }
  }

  // ── Download ────────────────────────────────────────────────────────────────

  async function downloadHtml() {
    if (!activeId) return
    try {
      // Fetch HTML and create a blob download — prevents Electron from navigating to http://
      const res = await fetch(`${backendUrl}/api/analysis/${activeId}/html`)
      const html = await res.text()
      const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
      const blobUrl = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = blobUrl
      a.download = `${activeTitle.replace(/[/\\:*?"<>|]/g, '_')}.html`
      a.click()
      setTimeout(() => URL.revokeObjectURL(blobUrl), 5000)
    } catch (e) {
      console.error('Download failed:', e)
    }
  }

  // ── Chat ────────────────────────────────────────────────────────────────────

  async function sendChat(messageOverride?: string) {
    const message = messageOverride || chatInput.trim()
    if (!message || chatStreaming || !activeId) return
    setChatInput('')

    const userMsg: ChatMessage = { role: 'user', content: message }
    setChatHistory(h => [...h, userMsg])
    setChatStreaming(true)
    setChatHistory(h => [...h, { role: 'assistant', content: '' }])

    try {
      const res = await fetch(`${backendUrl}/api/analysis/${activeId}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message,
          history: [...chatHistory, userMsg],
          api_key: apiKey || null,
        }),
      })
      const reader = res.body!.getReader()
      const decoder = new TextDecoder()
      let buf = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const parts = buf.split('\n\n')
        buf = parts.pop() || ''
        for (const part of parts) {
          const line = part.replace(/^data: /, '').trim()
          if (!line) continue
          try {
            const ev = JSON.parse(line)
            if (ev.type === 'chunk') {
              setChatHistory(h => {
                const copy = [...h]
                copy[copy.length - 1] = {
                  ...copy[copy.length - 1],
                  content: copy[copy.length - 1].content + ev.text,
                }
                return copy
              })
            }
          } catch { /* ignore */ }
        }
      }
    } catch (e) {
      const msg = String(e)
      if (/api.key|invalid|401|403|permission|authenticate/i.test(msg)) {
        alert('⚠️ Gemini API Key 无效或未配置\n\n请前往左侧「设置」页面填入正确的 API Key 后重试。')
      }
      setChatHistory(h => {
        const copy = [...h]
        copy[copy.length - 1] = { role: 'assistant', content: /api.key|invalid|401|403|permission|authenticate/i.test(msg) ? '⚠️ API Key 无效，请到「设置」页面更新后重试。' : `❌ 请求失败：${msg}` }
        return copy
      })
    }
    setChatStreaming(false)
  }

  // ── Creation: open modal ────────────────────────────────────────────────────

  async function openModal() {
    setShowModal(true)
    setStep('select')
    setSelectedIds([])
    setModalTitle('')
    setOutline('')
    setEditedOutline('')
    streamedHtmlRef.current = ''
    setStreamedHtmlDisplay('')
    setGenStatus('')
    mergedFlightsCache.current = null
    try {
      const res = await fetch(`${backendUrl}/api/report/list`)
      setReports(await res.json())
    } catch { /* ignore */ }
  }

  // ── Creation: fetch, merge, and deduplicate flights ───────────────────────
  //
  // Strategy:
  //  1. Fetch all flights from every selected report.
  //  2. Auto-infer date_ranges for any report that has none (e.g. single-route
  //     searches, weekday-filtered searches).  Without this, those flights would
  //     fall outside every range and be silently dropped by the analytics engine.
  //  3. Deduplicate: same itinerary fingerprint (trip_type + route + dates +
  //     airline + cabin + stops) → keep the lower price.
  //     IMPORTANT: trip_type and return_date are part of the key so that
  //     one-way and round-trip data are NEVER collapsed into each other.

  // Cluster a sorted list of dates into contiguous weekly windows.
  // Dates within 8 days of each other belong to the same cluster.
  function inferDateRanges(flights: any[]): { start: string; end: string }[] {
    const dates = [...new Set<string>(flights.map((f: any) => f.departure_date).filter(Boolean))].sort()
    if (!dates.length) return []
    const clusters: string[][] = [[dates[0]]]
    for (let i = 1; i < dates.length; i++) {
      const prev = clusters[clusters.length - 1]
      const gap = (new Date(dates[i]).getTime() - new Date(prev[prev.length - 1]).getTime()) / 86400000
      if (gap <= 8) prev.push(dates[i])
      else clusters.push([dates[i]])
    }
    return clusters.map(c => ({ start: c[0], end: c[c.length - 1] }))
  }

  // Remove ranges that are entirely contained within another range (deduplication).
  function deduplicateRanges(ranges: { start: string; end: string }[]): { start: string; end: string }[] {
    const sorted = [...ranges].sort((a, b) => a.start.localeCompare(b.start) || b.end.localeCompare(a.end))
    const result: { start: string; end: string }[] = []
    for (const r of sorted) {
      // Skip if already covered by a wider range in result
      const covered = result.some(e => e.start <= r.start && e.end >= r.end)
      if (!covered) result.push(r)
    }
    return result
  }

  async function fetchMergedFlights(): Promise<{ flights: object[]; date_ranges: object[]; rawCount: number; tripTypeCounts: Record<string, number> }> {
    let rawFlights: any[] = []
    const seenRanges = new Set<string>()
    const mergedRanges: { start: string; end: string }[] = []

    for (const rid of selectedIds) {
      try {
        const res = await fetch(`${backendUrl}/api/report/${rid}/flights`)
        if (res.ok) {
          const data = await res.json()
          const src: any[] = data.flights || []
          rawFlights = rawFlights.concat(src)

          // Use stored date_ranges; fall back to auto-inferred ranges when empty
          const reportRanges: { start: string; end: string }[] =
            data.date_ranges?.length ? data.date_ranges : inferDateRanges(src)

          for (const r of reportRanges) {
            const key = `${r.start}|${r.end}`
            if (!seenRanges.has(key)) { seenRanges.add(key); mergedRanges.push(r) }
          }
        }
      } catch { /* ignore */ }
    }

    const rawCount = rawFlights.length

    // Deduplicate: keep the lowest-price record per itinerary fingerprint.
    // KEY includes trip_type + return_date so round-trips and one-ways are
    // NEVER collapsed — they are distinct products with incomparable prices.
    const best = new Map<string, any>()
    for (const f of rawFlights) {
      const tripType  = f.trip_type  ?? 'one_way'
      const returnDt  = f.return_date ?? ''
      const key = `${tripType}|${f.origin}|${f.destination}|${f.departure_date}|${returnDt}|${f.airline_code}|${f.cabin}|${f.stops ?? 0}`
      const existing = best.get(key)
      if (!existing || (f.price > 0 && (!existing.price || f.price < existing.price))) best.set(key, f)
    }

    // Sort ranges chronologically; remove sub-ranges already covered by wider ones
    mergedRanges.sort((a, b) => a.start.localeCompare(b.start))
    const cleanRanges = deduplicateRanges(mergedRanges)

    const deduped = [...best.values()]

    // Warn if reports use different currencies (backend will auto-convert)
    const currencies = new Set<string>(rawFlights.map((f: any) => f.currency).filter(Boolean))
    if (currencies.size > 1) {
      console.warn(`混合货币: ${[...currencies].join(', ')} — 价格将自动折算为主要货币`)
    }

    // Trip-type breakdown for display
    const tripTypeCounts: Record<string, number> = {}
    for (const f of deduped) {
      const tt = f.trip_type ?? 'one_way'
      tripTypeCounts[tt] = (tripTypeCounts[tt] ?? 0) + 1
    }

    return { flights: deduped, date_ranges: cleanRanges, rawCount, tripTypeCounts }
  }

  // ── Creation: generate outline ─────────────────────────────────────────────

  async function handleGenerateOutline() {
    if (selectedIds.length === 0) return
    setGeneratingOutline(true)
    const { flights, date_ranges, rawCount, tripTypeCounts } = await fetchMergedFlights()

    if (flights.length === 0) {
      alert('选中的报告无原始航班数据（旧报告不含此数据）。\n请重新在"搜索 & 抓取"页生成报告后再分析。')
      setGeneratingOutline(false)
      return
    }

    // Auto-title: derive from selected reports' titles (shared prefix or joined)
    const selectedTitles = reports.filter(r => selectedIds.includes(r.report_id)).map(r => r.title)
    const autoTitle = selectedTitles.length === 1
      ? selectedTitles[0]
      : (() => {
          const prefix = selectedTitles.reduce((a, b) => {
            let i = 0
            while (i < a.length && i < b.length && a[i] === b[i]) i++
            return a.slice(0, i)
          }).replace(/[\s·—\-]+$/, '').trim()
          return prefix.length > 4 ? `${prefix} 综合分析` : `综合分析（${selectedTitles.length}份报告）`
        })()
    const title = modalTitle || autoTitle

    const ow = tripTypeCounts['one_way'] ?? 0
    const rt = tripTypeCounts['round_trip'] ?? 0
    console.log(`合并结果: 原始${rawCount}条 → 去重后${flights.length}条 (单程${ow} / 往返${rt})`)
    // Cache so handleGenerateReport doesn't need to re-fetch
    mergedFlightsCache.current = { flights, date_ranges }
    setModalTitle(title)

    try {
      const res = await fetch(`${backendUrl}/api/analysis/outline`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, flights, date_ranges, api_key: modalApiKey || null }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || '大纲生成失败')
      setOutline(data.outline || '')
      setEditedOutline(data.outline || '')
      setStep('outline')
    } catch (e) {
      const msg = String(e)
      if (/api.key|invalid|401|403|permission|authenticate/i.test(msg)) {
        alert('⚠️ Gemini API Key 无效或未配置\n\n请前往左侧「设置」页面填入正确的 API Key 后重试。')
      } else {
        alert(`大纲生成失败：${msg}`)
      }
    }
    setGeneratingOutline(false)
  }

  // ── Creation: generate full report ────────────────────────────────────────

  async function handleGenerateReport() {
    setStep('generating')
    streamedHtmlRef.current = ''
    setStreamedHtmlDisplay('')
    setGenStatus('正在生成分析报告，请稍候…')
    // Reuse cached result from outline step to avoid double-fetching
    const { flights, date_ranges } = mergedFlightsCache.current ?? await fetchMergedFlights()

    let finalId = ''
    let buf = ''

    try {
      const res = await fetch(`${backendUrl}/api/analysis/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: modalTitle,
          flights,
          outline: editedOutline,
          date_ranges,
          api_key: modalApiKey || null,
        }),
      })

      const reader = res.body!.getReader()
      const decoder = new TextDecoder()

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const parts = buf.split('\n\n')
        buf = parts.pop() || ''
        for (const part of parts) {
          const line = part.replace(/^data: /, '').trim()
          if (!line) continue
          try {
            const ev = JSON.parse(line)
            if (ev.type === 'chunk') {
              streamedHtmlRef.current += ev.text
              setStreamedHtmlDisplay(streamedHtmlRef.current)
            } else if (ev.type === 'done') {
              finalId = ev.analysis_id
              setGenStatus('✓ 报告生成完成！')
              setStep('done')
            } else if (ev.type === 'error') {
              setGenStatus(`❌ 生成失败：${ev.message}`)
            }
          } catch { /* ignore */ }
        }
      }
    } catch (e) {
      const msg = String(e)
      if (/api.key|invalid|401|403|permission|authenticate/i.test(msg)) {
        alert('⚠️ Gemini API Key 无效或未配置\n\n请前往左侧「设置」页面填入正确的 API Key 后重试。')
      }
      setGenStatus(`❌ 生成失败：${msg}`)
    }

    if (finalId) {
      await fetchAnalyses()
      setShowModal(false)
      // Load the newly generated report via blob URL
      await loadAnalysis(finalId, modalTitle)
    }
  }

  function toggleReport(id: string) {
    setSelectedIds(s => s.includes(id) ? s.filter(x => x !== id) : [...s, id])
  }

  const S = styles

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div style={S.page}>
      {/* Header */}
      <div style={S.header}>
        <span style={{ fontSize: 20 }}>🧠</span>
        <div>
          <h1 style={S.title}>AI 分析报告</h1>
          <p style={S.subtitle}>基于历史数据 · 国航竞争力深度分析 · AI 问答助手</p>
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
          <button style={S.btnSecondary} onClick={fetchAnalyses}>刷新</button>
          <button
            style={S.btnPrimary}
            onClick={openModal}
            disabled={status !== 'connected'}
          >
            + 新建分析
          </button>
        </div>
      </div>

      {/* Body: sidebar + content */}
      <div style={{ display: 'flex', flex: 1, minHeight: 0, overflow: 'hidden' }}>

        {/* ── Left sidebar: analysis list ─────────────────────────────────── */}
        <div style={S.sidebar}>
          {loadingList && (
            <p style={{ color: '#475569', textAlign: 'center', marginTop: 20, fontSize: 13 }}>加载中…</p>
          )}
          {!loadingList && analyses.length === 0 && (
            <div style={{ textAlign: 'center', marginTop: 60, color: '#475569' }}>
              <div style={{ fontSize: 36, marginBottom: 8 }}>📋</div>
              <p style={{ fontSize: 13 }}>暂无分析报告</p>
              <p style={{ fontSize: 11, marginTop: 4 }}>点击"新建分析"开始</p>
            </div>
          )}
          {analyses.map(a => (
            <div
              key={a.analysis_id}
              onClick={() => loadAnalysis(a.analysis_id, a.title)}
              style={{
                ...S.sidebarItem,
                borderColor: activeId === a.analysis_id ? '#3b82f6' : '#1e293b',
                background: activeId === a.analysis_id ? '#1e3a5f' : 'transparent',
              }}
            >
              <div style={{ fontSize: 13, color: '#e2e8f0', fontWeight: 500, marginBottom: 3, lineHeight: 1.4 }}>
                {a.title}
              </div>
              <div style={{ fontSize: 11, color: '#475569', marginBottom: 6 }}>{a.created_at}</div>
              <button
                style={S.btnDangerXS}
                onClick={(e) => deleteAnalysis(a.analysis_id, e)}
              >
                删除
              </button>
            </div>
          ))}
        </div>

        {/* ── Right: report + chat ─────────────────────────────────────────── */}
        {!activeId ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#475569' }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 48, marginBottom: 12 }}>🤖</div>
              <p style={{ fontSize: 15 }}>从左侧选择报告查看，或新建分析</p>
            </div>
          </div>
        ) : (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>

            {/* Report toolbar */}
            <div style={S.reportToolbar}>
              <span style={{ fontSize: 14, color: '#e2e8f0', fontWeight: 500, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {activeTitle}
              </span>
              <button
                style={{ ...S.btnGreen, padding: '6px 14px', fontSize: 12 }}
                onClick={downloadHtml}
                disabled={!activeId}
              >
                ↓ 下载 HTML
              </button>
            </div>

            {/* Report + Chat split */}
            <div style={{ flex: 1, display: 'flex', minHeight: 0, overflow: 'hidden' }}>

              {/* Report viewer — blob iframe (avoids Electron cross-origin CSP) */}
              <div style={{ flex: 1, overflow: 'hidden', position: 'relative' }}>
                {loadingActive && (
                  <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f8fafc', zIndex: 1 }}>
                    <div style={S.spinner} />
                    <span style={{ marginLeft: 10, color: '#6b7280' }}>加载报告…</span>
                  </div>
                )}
                {iframeSrc && (
                  <iframe
                    key={iframeSrc}
                    src={iframeSrc}
                    style={{ width: '100%', height: '100%', border: 'none', background: 'white' }}
                    title="Analysis report"
                    sandbox="allow-scripts"
                  />
                )}
                {!loadingActive && !iframeSrc && activeId && (
                  <p style={{ color: '#9ca3af', textAlign: 'center', marginTop: 60 }}>报告加载失败</p>
                )}
              </div>

              {/* Chat panel */}
              <div style={S.chatPanel}>
                <div style={S.chatHeader}>
                  <span style={{ fontSize: 12, color: '#94a3b8', fontWeight: 600 }}>💬 AI 助手</span>
                  <span style={{ fontSize: 11, color: '#475569' }}>基于报告内容解答</span>
                </div>

                <div style={S.chatMessages}>
                  {chatHistory.length === 0 && (
                    <div>
                      <p style={{ color: '#475569', fontSize: 12, marginBottom: 10 }}>
                        快速提问：
                      </p>
                      {SUGGESTED_QUESTIONS.map((q, i) => (
                        <button
                          key={i}
                          style={S.suggestBtn}
                          onClick={() => sendChat(q)}
                        >
                          {q}
                        </button>
                      ))}
                    </div>
                  )}
                  {chatHistory.map((msg, i) => (
                    <div key={i} style={{
                      ...S.chatBubble,
                      alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
                      background: msg.role === 'user' ? '#1e3a5f' : '#1e293b',
                      borderColor: msg.role === 'user' ? '#3b82f6' : '#334155',
                      maxWidth: '90%',
                    }}>
                      <span style={{ fontSize: 11, color: msg.role === 'user' ? '#93c5fd' : '#4ade80', fontWeight: 500 }}>
                        {msg.role === 'user' ? '你' : '🤖 AI 助手'}
                      </span>
                      <p style={{ margin: '4px 0 0', fontSize: 12, color: '#e2e8f0', whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>
                        {msg.content}
                        {i === chatHistory.length - 1 && msg.role === 'assistant' && chatStreaming && (
                          <span style={{ opacity: 0.5, animation: 'blink 1s infinite' }}>▋</span>
                        )}
                      </p>
                    </div>
                  ))}
                  <div ref={chatBottomRef} />
                </div>

                <div style={S.chatInputRow}>
                  <input
                    style={S.chatInput}
                    placeholder="输入问题，Enter 发送…"
                    value={chatInput}
                    onChange={e => setChatInput(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && !e.shiftKey && sendChat()}
                    disabled={chatStreaming}
                  />
                  <button
                    style={{ ...S.btnPrimary, padding: '7px 14px', fontSize: 12, flexShrink: 0 }}
                    onClick={() => sendChat()}
                    disabled={chatStreaming || !chatInput.trim()}
                  >
                    {chatStreaming ? '…' : '发送'}
                  </button>
                </div>
              </div>

            </div>
          </div>
        )}
      </div>

      {/* ── Creation Modal ─────────────────────────────────────────────────── */}
      {showModal && (
        <div style={S.modalOverlay}
             onClick={e => e.target === e.currentTarget && step !== 'generating' && setShowModal(false)}>
          <div style={S.modal}>

            {/* Modal header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18 }}>
              <h2 style={{ margin: 0, fontSize: 16, color: '#f8fafc' }}>
                {step === 'select'     ? '① 选择数据来源' :
                 step === 'outline'    ? '② 确认报告大纲' :
                 step === 'generating' ? '③ 生成中…'      : '✓ 生成完成'}
              </h2>
              {step !== 'generating' && (
                <button style={{ background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', fontSize: 18 }}
                        onClick={() => setShowModal(false)}>✕</button>
              )}
            </div>

            {/* ── STEP 1: select ── */}
            {step === 'select' && (
              <>
                {/* API Key info */}
                <div style={{ marginBottom: 14, background: '#0f172a', borderRadius: 8, padding: '10px 14px', border: '1px solid #1e293b' }}>
                  <div style={{ fontSize: 12, color: '#4ade80', marginBottom: 4 }}>
                    ✓ 后端已配置 Gemini API Key，无需填写
                  </div>
                  <div style={{ fontSize: 11, color: '#475569', marginBottom: 6 }}>如需覆盖（可选）：</div>
                  <input
                    style={S.inputField}
                    type="password"
                    placeholder="留空即可"
                    value={modalApiKey}
                    onChange={e => { setModalApiKey(e.target.value); localStorage.setItem('gemini_api_key', e.target.value) }}
                  />
                </div>

                <p style={{ fontSize: 13, color: '#94a3b8', marginBottom: 10 }}>
                  选择历史报告作为数据来源（可多选，航班数据与日期段将合并对比）：
                </p>
                {selectedIds.length >= 1 && (() => {
                  const sel = reports.filter(r => selectedIds.includes(r.report_id))
                  const total = sel.reduce((s, r) => s + (r.stats?.total_flights ?? r.total_flights), 0)
                  const currencies = new Set(sel.map(r => r.stats?.currency).filter(Boolean))
                  return (
                    <div style={{ marginBottom: 10, background: '#0f172a', borderRadius: 6, padding: '7px 12px', border: `1px solid ${currencies.size > 1 ? '#78350f' : '#1e3a5f'}`, fontSize: 11, color: currencies.size > 1 ? '#fbbf24' : '#60a5fa' }}>
                      已选 {selectedIds.length} 份报告 · 合计 {total} 条记录
                      {currencies.size > 1
                        ? <span> · ⚠ 货币不同 ({[...currencies].join('+')})，将自动折算为主要货币</span>
                        : selectedIds.length >= 2 && <span style={{ color: '#94a3b8' }}> · 自动去重，保留最低价</span>
                      }
                    </div>
                  )
                })()}

                <div style={{ maxHeight: 260, overflow: 'auto', marginBottom: 14 }}>
                  {reports.length === 0 && (
                    <p style={{ color: '#475569', fontSize: 13, textAlign: 'center', marginTop: 20 }}>
                      暂无报告，请先在"搜索 & 抓取"页生成
                    </p>
                  )}
                  {reports.map(r => (
                    <div
                      key={r.report_id}
                      onClick={() => r.has_flights && toggleReport(r.report_id)}
                      style={{
                        ...S.reportSelectItem,
                        borderColor: selectedIds.includes(r.report_id) ? '#3b82f6' : '#334155',
                        background: selectedIds.includes(r.report_id) ? '#1e3a5f' : 'transparent',
                        opacity: r.has_flights ? 1 : 0.45,
                        cursor: r.has_flights ? 'pointer' : 'not-allowed',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <div style={{
                          width: 16, height: 16, borderRadius: 4, flexShrink: 0,
                          border: `2px solid ${selectedIds.includes(r.report_id) ? '#3b82f6' : '#475569'}`,
                          background: selectedIds.includes(r.report_id) ? '#3b82f6' : 'transparent',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                        }}>
                          {selectedIds.includes(r.report_id) && <span style={{ color: 'white', fontSize: 10 }}>✓</span>}
                        </div>
                        <div style={{ flex: 1 }}>
                          <div style={{ fontSize: 13, color: '#e2e8f0' }}>{r.title}</div>
                          <div style={{ fontSize: 11, color: '#475569' }}>
                            {r.created_at} · {r.stats?.total_flights ?? r.total_flights} 航班
                            {!r.has_flights && <span style={{ color: '#f59e0b' }}> · ⚠ 需重新生成报告</span>}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>

                <div style={{ marginBottom: 16 }}>
                  <label style={{ fontSize: 12, color: '#64748b', display: 'block', marginBottom: 4 }}>报告标题（可留空自动生成）</label>
                  <input
                    style={S.inputField}
                    placeholder="例：LON出发航线竞争力分析 2026暑运"
                    value={modalTitle}
                    onChange={e => setModalTitle(e.target.value)}
                  />
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                  <button style={S.btnSecondary} onClick={() => setShowModal(false)}>取消</button>
                  <button
                    style={{ ...S.btnPrimary, opacity: selectedIds.length === 0 || generatingOutline ? 0.6 : 1 }}
                    disabled={selectedIds.length === 0 || generatingOutline}
                    onClick={handleGenerateOutline}
                  >
                    {generatingOutline ? '⏳ 生成大纲中…' : '生成大纲 →'}
                  </button>
                </div>
              </>
            )}

            {/* ── STEP 2: outline ── */}
            {step === 'outline' && (
              <>
                <p style={{ fontSize: 13, color: '#94a3b8', marginBottom: 10 }}>
                  AI 已生成报告大纲，可直接编辑调整后确认：
                </p>
                <textarea
                  style={{ ...S.inputField, height: 300, fontFamily: 'monospace', fontSize: 12, resize: 'vertical', lineHeight: 1.7 }}
                  value={editedOutline}
                  onChange={e => setEditedOutline(e.target.value)}
                />
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 14 }}>
                  <button style={S.btnSecondary} onClick={() => setStep('select')}>← 返回</button>
                  <button style={S.btnPrimary} onClick={handleGenerateReport}>
                    确认大纲，开始生成 →
                  </button>
                </div>
              </>
            )}

            {/* ── STEP 3/4: generating / done ── */}
            {(step === 'generating' || step === 'done') && (
              <>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
                  {step === 'generating' && <div style={S.spinner} />}
                  <span style={{ fontSize: 13, color: step === 'done' ? '#4ade80' : '#94a3b8' }}>
                    {genStatus || '生成中…'}
                  </span>
                </div>
                <div style={{
                  height: 180, overflow: 'hidden', background: '#0f172a',
                  borderRadius: 8, padding: '16px 20px', fontSize: 12, color: '#94a3b8',
                  border: '1px solid #1e293b', display: 'flex', flexDirection: 'column', gap: 8,
                }}>
                  {step === 'generating' ? (
                    <>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <div style={S.spinner} />
                        <span>正在计算竞争力数据 & 生成 AI 解读…</span>
                      </div>
                      <div style={{ color: '#475569', fontSize: 11, marginTop: 4 }}>
                        报告包含：KPI 总览 · 颜色编码价格表 · 高溢价预警 · AI 战略建议
                      </div>
                      {streamedHtmlDisplay && (
                        <div style={{ color: '#4ade80', fontSize: 11 }}>
                          ✓ 报告数据已生成（{Math.round(streamedHtmlDisplay.length / 1024)} KB）
                        </div>
                      )}
                    </>
                  ) : (
                    <div style={{ color: '#4ade80' }}>
                      ✓ 报告生成完成，共 {Math.round(streamedHtmlDisplay.length / 1024)} KB · 包含完整价格对比表格
                    </div>
                  )}
                </div>
                {step === 'done' && (
                  <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 14 }}>
                    <button style={S.btnPrimary} onClick={() => setShowModal(false)}>
                      查看完整报告 →
                    </button>
                  </div>
                )}
              </>
            )}

          </div>
        </div>
      )}
    </div>
  )
}


// ── Styles ────────────────────────────────────────────────────────────────────

const styles = {
  page: {
    height: '100%', display: 'flex', flexDirection: 'column',
    background: '#0f172a',
    fontFamily: '"PingFang SC","Microsoft YaHei",system-ui,sans-serif',
    color: '#e2e8f0', overflow: 'hidden',
  } as React.CSSProperties,

  header: {
    background: '#1e293b', borderBottom: '1px solid #334155',
    padding: '12px 20px', display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0,
  } as React.CSSProperties,
  title: { margin: 0, fontSize: 16, fontWeight: 500, color: '#f8fafc' } as React.CSSProperties,
  subtitle: { margin: '2px 0 0', fontSize: 12, color: '#64748b' } as React.CSSProperties,

  sidebar: {
    width: 240, borderRight: '1px solid #1e293b',
    overflow: 'auto', padding: '10px 8px', flexShrink: 0,
    display: 'flex', flexDirection: 'column', gap: 4,
  } as React.CSSProperties,
  sidebarItem: {
    borderRadius: 8, padding: '10px 12px', border: '1px solid transparent',
    cursor: 'pointer', transition: 'all 0.1s',
  } as React.CSSProperties,

  reportToolbar: {
    background: '#1e293b', borderBottom: '1px solid #334155',
    padding: '8px 16px', display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0,
  } as React.CSSProperties,

  reportContent: {
    background: 'white', borderRadius: 10, padding: 28,
    boxShadow: '0 2px 12px rgba(0,0,0,0.1)', maxWidth: 860, margin: '0 auto',
    color: '#1f2937', lineHeight: 1.8, fontSize: 14,
  } as React.CSSProperties,

  // Chat
  chatPanel: {
    width: 340, borderLeft: '1px solid #1e293b', background: '#070f1a',
    display: 'flex', flexDirection: 'column', flexShrink: 0, overflow: 'hidden',
  } as React.CSSProperties,
  chatHeader: {
    padding: '10px 14px', borderBottom: '1px solid #1e293b', flexShrink: 0,
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
  } as React.CSSProperties,
  chatMessages: {
    flex: 1, overflow: 'auto', padding: '10px 12px',
    display: 'flex', flexDirection: 'column', gap: 8,
  } as React.CSSProperties,
  chatBubble: {
    borderRadius: 10, padding: '8px 12px', border: '1px solid transparent',
  } as React.CSSProperties,
  suggestBtn: {
    display: 'block', width: '100%', textAlign: 'left' as const,
    background: '#1e293b', border: '1px solid #334155',
    borderRadius: 8, padding: '7px 10px', marginBottom: 5,
    color: '#93c5fd', fontSize: 12, cursor: 'pointer',
    transition: 'all 0.1s',
  } as React.CSSProperties,
  chatInputRow: {
    display: 'flex', gap: 6, padding: '10px 12px',
    borderTop: '1px solid #1e293b', flexShrink: 0,
  } as React.CSSProperties,
  chatInput: {
    flex: 1, background: '#1e293b', border: '1px solid #334155',
    borderRadius: 8, padding: '7px 10px', color: '#e2e8f0', fontSize: 12,
    outline: 'none', minWidth: 0,
  } as React.CSSProperties,

  // Modal
  modalOverlay: {
    position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)',
    display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100,
  } as React.CSSProperties,
  modal: {
    background: '#1e293b', border: '1px solid #334155', borderRadius: 14,
    padding: 26, width: 580, maxWidth: '92vw', maxHeight: '88vh', overflow: 'auto',
  } as React.CSSProperties,
  reportSelectItem: {
    borderRadius: 8, padding: '10px 12px', border: '1px solid #334155',
    marginBottom: 5, transition: 'all 0.1s',
  } as React.CSSProperties,
  inputField: {
    width: '100%', background: '#0f172a', border: '1px solid #334155',
    borderRadius: 8, padding: '8px 12px', color: '#e2e8f0', fontSize: 13,
    outline: 'none', boxSizing: 'border-box',
  } as React.CSSProperties,

  // Buttons
  btnPrimary: {
    background: 'linear-gradient(135deg,#3b82f6,#6366f1)',
    color: 'white', border: 'none', borderRadius: 8,
    padding: '8px 18px', cursor: 'pointer', fontSize: 13, fontWeight: 500,
  } as React.CSSProperties,
  btnGreen: {
    background: '#14532d', color: '#4ade80',
    border: '1px solid #166534', borderRadius: 6, cursor: 'pointer',
  } as React.CSSProperties,
  btnSecondary: {
    background: 'transparent', color: '#94a3b8', border: '1px solid #334155',
    borderRadius: 8, padding: '8px 14px', cursor: 'pointer', fontSize: 13,
  } as React.CSSProperties,
  btnDangerXS: {
    background: 'none', color: '#f87171', border: '1px solid #7f1d1d',
    borderRadius: 6, padding: '3px 8px', cursor: 'pointer', fontSize: 11,
  } as React.CSSProperties,

  spinner: {
    width: 16, height: 16, borderRadius: '50%',
    border: '2px solid #334155', borderTopColor: '#3b82f6',
    animation: 'spin 0.8s linear infinite', flexShrink: 0,
  } as React.CSSProperties,
} as const
