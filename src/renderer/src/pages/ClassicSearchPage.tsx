import { useState, useRef, useCallback, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { useBackend } from '../hooks/useBackend'

// ── Types ─────────────────────────────────────────────────────────────────────

// A date entry is either a single date or an inclusive range
type DateEntry =
  | { id: string; type: 'single'; date: string }
  | { id: string; type: 'range'; start: string; end: string }

function entryLabel(e: DateEntry): string {
  if (e.type === 'single') return e.date
  const days = Math.round((new Date(e.end).getTime() - new Date(e.start).getTime()) / 86400000) + 1
  const fmt = (d: string) => d.slice(5)   // "MM-DD"
  return `${fmt(e.start)}–${fmt(e.end)} (${days}天)`
}

function expandEntries(entries: DateEntry[]): string[] {
  const out = new Set<string>()
  for (const e of entries) {
    if (e.type === 'single') {
      out.add(e.date)
    } else {
      const cur = new Date(e.start + 'T00:00:00')
      const last = new Date(e.end + 'T00:00:00')
      let guard = 0
      while (cur <= last && guard++ < 180) {
        out.add(cur.toISOString().split('T')[0])
        cur.setDate(cur.getDate() + 1)
      }
    }
  }
  return [...out].sort()
}

interface FlightResult {
  origin: string
  destination: string
  departure_date: string
  airline: string
  airline_code: string
  stops: number
  is_direct: boolean
  total_duration: string
  price: number
  currency: string
  cabin: string
  leg?: 'out' | 'ret'
}

interface SSEEvent {
  type: 'progress' | 'result' | 'done' | 'error'
  message?: string
  current?: number
  total?: number
  date?: string
  leg?: 'out' | 'ret'
  flights?: FlightResult[]
  cached?: boolean
  total_flights?: number
}

interface ODPair { id: string; origin: string; destination: string }

const CABIN_LABELS: Record<string, string> = { Y: '经济舱', C: '商务舱', F: '头等舱' }
const CURRENCY_LIST = ['HKD', 'USD', 'EUR', 'GBP', 'CNY']
const WEEKDAY_LABELS = ['一', '二', '三', '四', '五', '六', '日']

function uid() { return Math.random().toString(36).slice(2) }

function dateRange(start: string, end: string): string[] {
  if (!start || !end) return []
  const out: string[] = []
  const cur = new Date(start)
  const last = new Date(end)
  while (cur <= last && out.length < 92) {
    out.push(cur.toISOString().split('T')[0])
    cur.setDate(cur.getDate() + 1)
  }
  return out
}

function applyWeekdayFilter(dates: string[], weekdays: number[]): string[] {
  if (!weekdays.length) return dates
  const days = new Set(weekdays)
  return dates.filter(d => {
    const wd = (new Date(d).getDay() + 6) % 7  // Mon=0 ... Sun=6
    return days.has(wd)
  })
}

function addDays(dateStr: string, days: number): string {
  const d = new Date(dateStr)
  d.setDate(d.getDate() + days)
  return d.toISOString().split('T')[0]
}

// ── Shared helpers ────────────────────────────────────────────────────────────

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label style={{ display: 'block', fontSize: 12, color: '#64748b', marginBottom: 5 }}>{label}</label>
      {children}
    </div>
  )
}

function ProgressBar({ current, total, message }: { current: number; total: number; message: string }) {
  const pct = total ? Math.round((current / total) * 100) : 0
  return (
    <div style={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 10, padding: '14px 20px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
        <span style={{ color: '#94a3b8', fontSize: 13 }}>{message}</span>
        <span style={{ color: '#475569', fontSize: 12 }}>{current}/{total} ({pct}%)</span>
      </div>
      <div style={{ background: '#0f172a', borderRadius: 4, height: 8, overflow: 'hidden' }}>
        <div style={{
          height: '100%', width: `${pct}%`,
          background: 'linear-gradient(90deg,#3b82f6,#6366f1)',
          transition: 'width 0.3s',
        }} />
      </div>
    </div>
  )
}

// ── SINGLE SEARCH MODE ────────────────────────────────────────────────────────

interface SingleInit {
  origin: string
  destination: string
  dateStart: string
  dateEnd: string
  weekdayFilter: number[]
  cabin: string
  currency: string
  tripType?: 'one_way' | 'round_trip'
  returnDateStart?: string
  returnDateEnd?: string
}

function SingleSearch({ backendUrl, init }: { backendUrl: string; init?: SingleInit }) {
  const [tripType, setTripType]   = useState<'one_way' | 'round_trip'>(init?.tripType || 'one_way')
  const [origin, setOrigin]       = useState(init?.origin || 'LON')
  const [dest, setDest]           = useState(init?.destination || 'BJS')
  const [dateStart, setDateStart] = useState(init?.dateStart || '2026-06-01')
  const [dateEnd, setDateEnd]     = useState(init?.dateEnd   || '2026-06-07')
  const [returnDate, setReturnDate] = useState(
    init?.returnDateStart || (init?.dateStart ? addDays(init.dateStart, 7) : '2026-06-14')
  )
  const [weekdays, setWeekdays]   = useState<number[]>(init?.weekdayFilter || [])
  const [cabin, setCabin]         = useState(init?.cabin    || 'Y')
  const [currency, setCurrency]   = useState(init?.currency || 'HKD')
  const [showBrowser, setShowBrowser] = useState(false)
  const [dryRun, setDryRun]       = useState(false)

  const [searching, setSearching]   = useState(false)
  const [progress, setProgress]     = useState({ msg: '', cur: 0, total: 0 })
  const [resultsByKey, setResultsByKey] = useState<Record<string, FlightResult[]>>({})
  const [done, setDone]             = useState(false)
  const [genRep, setGenRep]         = useState(false)
  const [reportId, setReportId]     = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  // Update return date when departure date changes (+7 days default)
  useEffect(() => {
    if (tripType === 'round_trip') {
      setReturnDate(addDays(dateStart, 7))
    }
  }, [dateStart, tripType])

  const allDates  = dateRange(dateStart, dateEnd)
  const filtDates = applyWeekdayFilter(allDates, weekdays)
  const allFlights = Object.values(resultsByKey).flat()

  function toggleWeekday(wd: number) {
    setWeekdays(prev => prev.includes(wd) ? prev.filter(x => x !== wd) : [...prev, wd].sort())
  }

  function getDateCount() {
    if (tripType === 'round_trip') return 1  // single departure + return pair
    return filtDates.length
  }

  async function handleSearch() {
    setSearching(true)
    setResultsByKey({})
    setDone(false)
    setReportId(null)
    const dates = tripType === 'round_trip' ? [dateStart] : filtDates
    setProgress({ msg: '准备中…', cur: 0, total: tripType === 'round_trip' ? 2 : dates.length })
    abortRef.current = new AbortController()

    try {
      const body: Record<string, unknown> = {
        origin, destination: dest, dates, cabin, currency,
        trip_type: tripType,
        weekday_filter: weekdays,
        show_browser: showBrowser,
        dry_run: dryRun,
      }
      if (tripType === 'round_trip') {
        body.return_dates = [returnDate]
      }

      const res = await fetch(`${backendUrl}/api/search/classic`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: abortRef.current.signal,
      })
      const reader = res.body!.getReader()
      const dec = new TextDecoder()
      let buf = ''
      while (true) {
        const { done: d, value } = await reader.read()
        if (d) break
        buf += dec.decode(value, { stream: true })
        const lines = buf.split('\n')
        buf = lines.pop() ?? ''
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const evt: SSEEvent = JSON.parse(line.slice(6))
            if (evt.type === 'progress')
              setProgress({ msg: evt.message!, cur: evt.current!, total: evt.total! })
            else if (evt.type === 'result' && evt.flights) {
              const key = evt.leg ? `${evt.date}-${evt.leg}` : evt.date!
              setResultsByKey(p => ({ ...p, [key]: evt.flights! }))
            }
            else if (evt.type === 'done') setDone(true)
          } catch { /* ok */ }
        }
      }
    } catch (err: any) { if (err.name !== 'AbortError') console.error(err) }
    setSearching(false)
    setDone(true)
  }

  async function generateReport() {
    if (!allFlights.length) return
    setGenRep(true)
    try {
      const label = tripType === 'round_trip'
        ? `${origin}→${dest} 去程${dateStart} 返程${returnDate}`
        : `${origin}→${dest} ${dateStart}~${dateEnd}${weekdays.length ? ` 周${weekdays.map(w => WEEKDAY_LABELS[w]).join('/')}` : ''}`
      const title = `${label} ${CABIN_LABELS[cabin]}`
      const res = await fetch(`${backendUrl}/api/report/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, flights: allFlights, api_key: localStorage.getItem('gemini_api_key') || null }),
      })
      const data = await res.json()
      setReportId(data.report_id)
      window.open(`${backendUrl}/api/report/${data.report_id}/excel`, '_blank')
    } catch (err) { console.error(err) }
    setGenRep(false)
  }

  const S = singleStyles

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={S.card}>

        {/* Trip type toggle */}
        <div style={{ display: 'flex', gap: 0, marginBottom: 18, background: '#0f172a', borderRadius: 8, padding: 3, width: 'fit-content' }}>
          {([['one_way', '单程 One-Way'], ['round_trip', '往返 Round-Trip']] as const).map(([t, label]) => (
            <button key={t} onClick={() => setTripType(t)} style={{
              padding: '6px 16px', fontSize: 12, cursor: 'pointer', border: 'none', borderRadius: 6,
              fontWeight: 500,
              background: tripType === t ? 'linear-gradient(135deg,#3b82f6,#6366f1)' : 'transparent',
              color: tripType === t ? '#fff' : '#64748b',
            }}>{label}</button>
          ))}
        </div>

        {/* Route + dates */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: '10px 18px' }}>
          <Field label="出发 (IATA)">
            <input style={S.input} value={origin} maxLength={3}
              onChange={e => setOrigin(e.target.value.toUpperCase())} placeholder="LON" />
          </Field>
          <Field label="到达 (IATA)">
            <input style={S.input} value={dest} maxLength={3}
              onChange={e => setDest(e.target.value.toUpperCase())} placeholder="BJS" />
          </Field>
          <Field label="舱位">
            <select style={S.input} value={cabin} onChange={e => setCabin(e.target.value)}>
              {Object.entries(CABIN_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </Field>

          {tripType === 'one_way' ? (
            <>
              <Field label="出发日期（起）">
                <input style={S.input} type="date" value={dateStart}
                  onChange={e => setDateStart(e.target.value)} />
              </Field>
              <Field label="出发日期（止）">
                <input style={S.input} type="date" value={dateEnd}
                  onChange={e => setDateEnd(e.target.value)} />
              </Field>
              <Field label="币种">
                <select style={S.input} value={currency} onChange={e => setCurrency(e.target.value)}>
                  {CURRENCY_LIST.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </Field>
            </>
          ) : (
            <>
              <Field label="去程日期">
                <input style={S.input} type="date" value={dateStart}
                  onChange={e => setDateStart(e.target.value)} />
              </Field>
              <Field label="返程日期">
                <input style={S.input} type="date" value={returnDate}
                  onChange={e => setReturnDate(e.target.value)} />
              </Field>
              <Field label="币种">
                <select style={S.input} value={currency} onChange={e => setCurrency(e.target.value)}>
                  {CURRENCY_LIST.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </Field>
            </>
          )}
        </div>

        {/* Weekday filter — one-way only */}
        {tripType === 'one_way' && (
          <div style={{ marginTop: 14 }}>
            <div style={{ fontSize: 12, color: '#64748b', marginBottom: 7 }}>
              星期筛选 <span style={{ color: '#334155' }}>（留空=全部）</span>
            </div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
              {WEEKDAY_LABELS.map((label, idx) => {
                const active = weekdays.includes(idx)
                return (
                  <button key={idx} onClick={() => toggleWeekday(idx)} style={{
                    width: 36, height: 30, border: `1px solid ${active ? '#3b82f6' : '#334155'}`,
                    borderRadius: 6, fontSize: 12, cursor: 'pointer',
                    background: active ? 'linear-gradient(135deg,#2563eb,#4f46e5)' : '#0f172a',
                    color: active ? '#fff' : '#64748b', fontWeight: active ? 600 : 400,
                  }}>
                    {label}
                  </button>
                )
              })}
              {weekdays.length > 0 && (
                <button onClick={() => setWeekdays([])} style={{
                  fontSize: 11, color: '#475569', background: 'none', border: '1px solid #334155',
                  borderRadius: 6, padding: '3px 8px', cursor: 'pointer',
                }}>
                  清除
                </button>
              )}
              <span style={{ fontSize: 12, color: '#475569', marginLeft: 4 }}>
                {filtDates.length} 天
                {allDates.length !== filtDates.length && ` (共${allDates.length}天，筛选后${filtDates.length}天)`}
              </span>
            </div>
          </div>
        )}

        {/* Options row */}
        <div style={{ marginTop: 14, display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'center' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 5, color: '#64748b', fontSize: 12, cursor: 'pointer' }}>
            <input type="checkbox" checked={showBrowser} onChange={e => setShowBrowser(e.target.checked)} />
            显示浏览器窗口
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 5, color: '#64748b', fontSize: 12, cursor: 'pointer' }}>
            <input type="checkbox" checked={dryRun} onChange={e => setDryRun(e.target.checked)} />
            演示模式
          </label>
        </div>

        {/* Search button */}
        <div style={{ marginTop: 14 }}>
          {!searching
            ? <button style={S.btnPrimary} onClick={handleSearch}
                disabled={tripType === 'one_way' ? filtDates.length === 0 : !dateStart}>
                🔍 开始搜索 ({tripType === 'one_way' ? `${filtDates.length}天` : '去+返 共2次'})
              </button>
            : <button style={{ ...S.btnPrimary, background: '#7f1d1d' }}
                onClick={() => abortRef.current?.abort()}>
                ■ 停止
              </button>
          }
        </div>
      </div>

      {(searching || progress.total > 0) && <ProgressBar current={progress.cur} total={progress.total} message={progress.msg} />}

      {done && allFlights.length > 0 && (
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <button style={{ ...S.btnPrimary, background: 'linear-gradient(135deg,#dc2626,#b91c1c)', opacity: genRep ? 0.6 : 1 }}
            disabled={genRep} onClick={generateReport}>
            {genRep ? '生成中…' : '📊 生成Excel报告'}
          </button>
          {reportId && <span style={{ color: '#4ade80', fontSize: 13 }}>✓ 报告已下载（ID: {reportId}）</span>}
          <span style={{ color: '#475569', fontSize: 12 }}>共 {allFlights.length} 个航班</span>
        </div>
      )}

      {Object.entries(resultsByKey).sort().map(([key, flights]) => {
        const isReturn = key.endsWith('-ret')
        const dateLabel = key.replace(/-(?:out|ret)$/, '')
        return (
          <div key={key} style={S.card}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
              <span style={{ fontWeight: 600, color: '#e2e8f0' }}>
                {dateLabel}
                {isReturn && <span style={{ marginLeft: 8, fontSize: 11, color: '#fb923c', background: '#431407', padding: '1px 7px', borderRadius: 10 }}>返程</span>}
                {key.endsWith('-out') && <span style={{ marginLeft: 8, fontSize: 11, color: '#4ade80', background: '#14532d', padding: '1px 7px', borderRadius: 10 }}>去程</span>}
              </span>
              <span style={{ fontSize: 12, color: '#475569' }}>{flights.length} 个航班</span>
            </div>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ background: '#0f172a', color: '#64748b' }}>
                    {['航司', '直/转', '时长', '价格'].map(h => (
                      <th key={h} style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 500 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {flights.slice(0, 15).map((f, i) => (
                    <tr key={i} style={{ borderTop: '1px solid #1e293b' }}>
                      <td style={{ padding: '7px 12px', color: '#e2e8f0' }}>{f.airline}</td>
                      <td style={{ padding: '7px 12px' }}>
                        <span style={{ background: f.is_direct ? '#14532d' : '#431407', color: f.is_direct ? '#4ade80' : '#fb923c', padding: '1px 7px', borderRadius: 10, fontSize: 11 }}>
                          {f.is_direct ? '直飞' : `+${f.stops}`}
                        </span>
                      </td>
                      <td style={{ padding: '7px 12px', color: '#94a3b8' }}>{f.total_duration || '—'}</td>
                      <td style={{ padding: '7px 12px', color: '#fbbf24', fontWeight: 600 }}>{f.currency} {f.price.toFixed(0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {flights.length > 15 && <div style={{ textAlign: 'center', padding: '8px', color: '#475569', fontSize: 12 }}>还有 {flights.length - 15} 个航班…</div>}
            </div>
          </div>
        )
      })}
    </div>
  )
}

const singleStyles = {
  card: { background: '#1e293b', border: '1px solid #334155', borderRadius: 10, padding: '18px 22px' } as React.CSSProperties,
  cardTitle: { margin: '0 0 14px', fontSize: 13, fontWeight: 600, color: '#94a3b8', textTransform: 'uppercase' as const, letterSpacing: '0.06em' } as React.CSSProperties,
  input: { width: '100%', background: '#0f172a', border: '1px solid #334155', borderRadius: 6, padding: '7px 11px', color: '#e2e8f0', fontSize: 13, outline: 'none', boxSizing: 'border-box' as const } as React.CSSProperties,
  btnPrimary: { background: 'linear-gradient(135deg,#3b82f6,#6366f1)', color: 'white', border: 'none', borderRadius: 8, padding: '9px 22px', fontSize: 13, cursor: 'pointer', fontWeight: 500 } as React.CSSProperties,
}

// ── BATCH SEARCH MODE ─────────────────────────────────────────────────────────

interface BatchInit {
  routes: { origin: string; destination: string }[]
  dates: string[]
  dateRanges?: { start: string; end: string }[]
  cabins: string[]
  currency: string
  tripType?: 'one_way' | 'round_trip'
  returnDates?: string[]
}

// City group presets for quick destination selection
const CITY_GROUPS: Record<string, { label: string; cities: string[] }> = {
  '主要内地': { label: '主要内地 (6)', cities: ['BJS','SHA','CAN','CTU','SZX','HGH'] },
  '北方城市': { label: '北方 (5)', cities: ['BJS','TSN','DLC','SHE','HRB'] },
  '华南城市': { label: '华南 (4)', cities: ['CAN','SZX','XMN','HKG'] },
  '更多内地': { label: '更多内地 (6)', cities: ['CGO','CSX','FOC','WUH','XIY','KMG'] },
  '全部内地': { label: '全部内地 (12)', cities: ['BJS','SHA','CAN','CTU','SZX','HGH','CGO','CSX','FOC','WUH','XIY','KMG'] },
}

// Date presets (computed relative to current year)
function getDatePresets(): Record<string, string[]> {
  const y = new Date().getFullYear()
  const n = y + 1
  return {
    '今夏':     [`${y}-06-10`,`${y}-07-15`,`${y}-08-12`,`${y}-09-09`],
    'Q3':       [`${y}-07-15`,`${y}-08-12`,`${y}-09-09`],
    '下半年':   [`${y}-07-15`,`${y}-08-12`,`${y}-09-09`,`${y}-10-14`,`${y}-11-11`,`${y}-12-09`],
    '明年上半': [`${n}-01-14`,`${n}-02-11`,`${n}-03-11`,`${n}-04-08`,`${n}-05-13`,`${n}-06-10`],
  }
}

// Chip component reused below
function Chip({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      background: '#0f172a', border: '1px solid #334155', borderRadius: 20,
      padding: '3px 10px 3px 12px', fontSize: 13, color: '#e2e8f0',
    }}>
      {label}
      <button onClick={onRemove} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#475569', fontSize: 14, lineHeight: 1, padding: 0 }}>×</button>
    </span>
  )
}

function IataInput({ placeholder, onAdd }: { placeholder: string; onAdd: (v: string) => void }) {
  const [val, setVal] = useState('')
  function submit() {
    const v = val.trim().toUpperCase()
    if (v.length === 3) { onAdd(v); setVal('') }
  }
  return (
    <div style={{ display: 'inline-flex', gap: 4 }}>
      <input
        style={{ ...batchStyles.input, width: 72, color: val ? '#e2e8f0' : '#475569' } as React.CSSProperties}
        value={val} maxLength={3} placeholder={placeholder}
        onChange={e => setVal(e.target.value.toUpperCase())}
        onKeyDown={e => e.key === 'Enter' && submit()}
      />
      <button style={batchStyles.addBtn} onClick={submit}>+</button>
    </div>
  )
}

function BatchSearch({ backendUrl, init }: { backendUrl: string; init?: BatchInit }) {
  // Extract unique origins and destinations from init routes
  const [origins, setOrigins] = useState<string[]>(() => {
    if (init?.routes?.length) return [...new Set(init.routes.map(r => r.origin))]
    return ['LON']
  })
  const [dests, setDests] = useState<string[]>(() => {
    if (init?.routes?.length) return [...new Set(init.routes.map(r => r.destination))]
    return ['BJS', 'CTU', 'PVG']
  })
  const [dateEntries, setDateEntries] = useState<DateEntry[]>(() => {
    // AI sent date ranges → use as range entries
    if (init?.dateRanges?.length) {
      return init.dateRanges.map(r => ({ id: uid(), type: 'range' as const, start: r.start, end: r.end }))
    }
    // Flat dates (specific_dates from AI, or default)
    const src = init?.dates?.length ? init.dates : ['2026-06-10', '2026-07-15', '2026-08-12', '2026-09-16']
    return src.map(d => ({ id: uid(), type: 'single' as const, date: d }))
  })
  const [dateMode, setDateMode] = useState<'single' | 'range'>('single')
  const [newSingle, setNewSingle] = useState('')
  const [newRangeStart, setNewRangeStart] = useState('')
  const [newRangeEnd, setNewRangeEnd] = useState('')
  const [cabins, setCabins] = useState<Record<string, boolean>>(() => {
    if (init?.cabins?.length) {
      return { Y: init.cabins.includes('Y'), C: init.cabins.includes('C'), F: init.cabins.includes('F') }
    }
    return { Y: true, C: true }
  })
  const [currency, setCurrency] = useState(init?.currency || 'HKD')
  const [batchTripType] = useState<'one_way' | 'round_trip'>(init?.tripType || 'one_way')
  const [batchReturnDates] = useState<string[]>(init?.returnDates || [])
  const [dryRun, setDryRun] = useState(false)
  const [running, setRunning] = useState(false)
  const [progress, setProgress] = useState({ msg: '', cur: 0, total: 0 })
  const [log, setLog] = useState<string[]>([])
  const [allFlights, setAllFlights] = useState<FlightResult[]>([])
  const [reportId, setReportId] = useState<string | null>(null)
  const [genRep, setGenRep] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  const addLog = useCallback((s: string) => setLog(prev => [...prev.slice(-80), s]), [])

  // Computed routes matrix
  const routes = origins.flatMap(o => dests.map(d => ({ origin: o, destination: d })))
  const selectedCabins = Object.keys(cabins).filter(k => cabins[k])
  const expandedDates = expandEntries(dateEntries)
  const totalQ = routes.length * expandedDates.length * selectedCabins.length

  function addCityGroup(groupKey: string) {
    const cities = CITY_GROUPS[groupKey].cities
    setDests(prev => {
      const merged = [...prev]
      cities.forEach(c => { if (!merged.includes(c)) merged.push(c) })
      return merged
    })
  }

  function addSingleDate() {
    if (!newSingle) return
    const exists = dateEntries.some(e => e.type === 'single' && e.date === newSingle)
    if (!exists) {
      setDateEntries(prev => [...prev, { id: uid(), type: 'single', date: newSingle }])
      setNewSingle('')
    }
  }

  function addRangeDate() {
    if (!newRangeStart || !newRangeEnd || newRangeEnd < newRangeStart) return
    setDateEntries(prev => [...prev, { id: uid(), type: 'range', start: newRangeStart, end: newRangeEnd }])
    setNewRangeStart('')
    setNewRangeEnd('')
  }

  function removeEntry(id: string) {
    setDateEntries(prev => prev.filter(e => e.id !== id))
  }

  function applyDatePreset(key: string) {
    setDateEntries(getDatePresets()[key].map(d => ({ id: uid(), type: 'single' as const, date: d })))
  }

  async function runBatch() {
    if (!routes.length || !expandedDates.length || !selectedCabins.length) return

    const dates = expandedDates   // flat expanded list for the API
    const total = routes.length * selectedCabins.length
    setRunning(true)
    setAllFlights([])
    setReportId(null)
    setLog([])
    abortRef.current = new AbortController()

    let cur = 0
    const collected: FlightResult[] = []

    for (const cabin of selectedCabins) {
      for (const route of routes) {
        if (abortRef.current.signal.aborted) break
        cur++
        const label = `[${cur}/${total}] ${route.origin}→${route.destination} ${CABIN_LABELS[cabin]}`
        setProgress({ msg: `${label}…`, cur, total })
        addLog(`▶ ${label}`)

        try {
          const res = await fetch(`${backendUrl}/api/search/classic`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              origin: route.origin, destination: route.destination,
              dates, cabin, currency,
              trip_type: batchTripType,
              return_dates: batchTripType === 'round_trip' ? batchReturnDates : [],
              dry_run: dryRun,
              weekday_filter: [], show_browser: false,
            }),
            signal: abortRef.current.signal,
          })

          const reader = res.body!.getReader()
          const dec = new TextDecoder()
          let buf = ''
          let routeFlights = 0
          while (true) {
            const { done, value } = await reader.read()
            if (done) break
            buf += dec.decode(value, { stream: true })
            const lines = buf.split('\n')
            buf = lines.pop() ?? ''
            for (const line of lines) {
              if (!line.startsWith('data: ')) continue
              try {
                const evt: SSEEvent = JSON.parse(line.slice(6))
                if (evt.type === 'result' && evt.flights?.length) {
                  collected.push(...evt.flights)
                  routeFlights += evt.flights.length
                } else if (evt.type === 'progress' && evt.message) {
                  setProgress(p => ({ ...p, msg: `${label} — ${evt.message}` }))
                }
              } catch { /* ok */ }
            }
          }
          addLog(`  ✓ ${routeFlights} 个航班`)
        } catch (err: any) {
          if (err.name === 'AbortError') { addLog('已停止'); break }
          addLog(`  ✗ 错误: ${err}`)
        }

        setAllFlights([...collected])
        await new Promise(r => setTimeout(r, 400))
      }
      if (abortRef.current.signal.aborted) break
    }

    setProgress({ msg: '完成', cur: total, total })
    setAllFlights([...collected])
    addLog(`\n✅ 完成，共 ${collected.length} 个航班`)
    setRunning(false)
  }

  async function generateReport() {
    if (!allFlights.length) return
    setGenRep(true)
    setReportId(null)
    try {
      const origStr = origins.join('/')
      const dstStr = dests.length <= 4 ? dests.join('/') : `${dests.length}个目的地`
      const d0 = expandedDates[0], dN = expandedDates[expandedDates.length - 1]
      const title = `批量比价 ${origStr}→${dstStr} ${d0}~${dN}`
      const apiKey = localStorage.getItem('gemini_api_key') || undefined

      // Extract date ranges for period-aggregated matrix view
      const rangesForReport = dateEntries
        .filter(e => e.type === 'range')
        .map(e => ({ start: (e as Extract<DateEntry, {type:'range'}>).start, end: (e as Extract<DateEntry, {type:'range'}>).end }))

      const res = await fetch(`${backendUrl}/api/report/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title, flights: allFlights,
          date_ranges: rangesForReport,
          api_key: apiKey || null,
        }),
      })
      const data = await res.json()
      setReportId(data.report_id)
      addLog(`📊 报告已生成 ID: ${data.report_id}`)
      window.open(`${backendUrl}/api/report/${data.report_id}/excel`, '_blank')
    } catch (err) {
      addLog(`报告生成失败: ${err}`)
    }
    setGenRep(false)
  }

  const S = batchStyles

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>

      {/* Origins */}
      <div style={S.card}>
        <div style={S.sectionHeader}>
          <span style={S.cardTitle}>出发城市</span>
          <span style={S.dimText}>{origins.length} 个出发地</span>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
          {origins.map(o => (
            <Chip key={o} label={o} onRemove={() => setOrigins(prev => prev.filter(x => x !== o))} />
          ))}
          <IataInput placeholder="LON" onAdd={v => { if (!origins.includes(v)) setOrigins(p => [...p, v]) }} />
        </div>
      </div>

      {/* Destinations */}
      <div style={S.card}>
        <div style={S.sectionHeader}>
          <span style={S.cardTitle}>目的地</span>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {Object.entries(CITY_GROUPS).map(([key, { label }]) => (
              <button key={key} style={S.presetBtn} onClick={() => addCityGroup(key)}>{label}</button>
            ))}
            {dests.length > 0 && (
              <button style={{ ...S.presetBtn, background: '#7f1d1d', borderColor: '#991b1b' }}
                onClick={() => setDests([])}>清空</button>
            )}
          </div>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
          {dests.map(d => (
            <Chip key={d} label={d} onRemove={() => setDests(prev => prev.filter(x => x !== d))} />
          ))}
          <IataInput placeholder="BJS" onAdd={v => { if (!dests.includes(v)) setDests(p => [...p, v]) }} />
        </div>
        {origins.length > 0 && dests.length > 0 && (
          <div style={{ marginTop: 8, fontSize: 12, color: '#475569' }}>
            {origins.length} × {dests.length} = <strong style={{ color: '#94a3b8' }}>{routes.length} 条航线</strong>：{routes.slice(0, 6).map(r => `${r.origin}-${r.destination}`).join('，')}{routes.length > 6 ? ` … 共${routes.length}条` : ''}
          </div>
        )}
      </div>

      {/* Dates */}
      <div style={S.card}>
        <div style={S.sectionHeader}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={S.cardTitle}>搜索日期</span>
            <span style={S.dimText}>{expandedDates.length} 天</span>
            {/* Mode toggle */}
            <div style={{ display: 'flex', background: '#0f172a', borderRadius: 6, padding: 2 }}>
              {(['single', 'range'] as const).map(m => (
                <button key={m} onClick={() => setDateMode(m)} style={{
                  padding: '3px 10px', fontSize: 11, border: 'none', borderRadius: 5, cursor: 'pointer',
                  background: dateMode === m ? '#2563eb' : 'transparent',
                  color: dateMode === m ? '#fff' : '#64748b', fontWeight: dateMode === m ? 600 : 400,
                }}>
                  {m === 'single' ? '单日' : '日期段'}
                </button>
              ))}
            </div>
          </div>
          {/* Presets */}
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {Object.keys(getDatePresets()).map(key => (
              <button key={key} style={S.presetBtn} onClick={() => applyDatePreset(key)}>{key}</button>
            ))}
          </div>
        </div>

        {/* Date entry chips */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center', marginBottom: 12, minHeight: 36 }}>
          {dateEntries.map(e => (
            <Chip key={e.id} label={entryLabel(e)} onRemove={() => removeEntry(e.id)} />
          ))}
          {dateEntries.length === 0 && (
            <span style={{ color: '#334155', fontSize: 12 }}>尚未添加日期</span>
          )}
        </div>

        {/* Input area */}
        {dateMode === 'single' ? (
          <div style={{ display: 'flex', gap: 8 }}>
            <input style={{ ...S.input, flex: 1 }} type="date" value={newSingle}
              onChange={e => setNewSingle(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && addSingleDate()} />
            <button style={S.addBtn} onClick={addSingleDate} disabled={!newSingle}>+ 添加单日</button>
          </div>
        ) : (
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <input style={{ ...S.input, width: 150 }} type="date" value={newRangeStart}
              onChange={e => setNewRangeStart(e.target.value)} />
            <span style={{ color: '#475569', fontSize: 13 }}>至</span>
            <input style={{ ...S.input, width: 150 }} type="date" value={newRangeEnd}
              onChange={e => setNewRangeEnd(e.target.value)} />
            {newRangeStart && newRangeEnd && newRangeEnd >= newRangeStart && (
              <span style={{ fontSize: 12, color: '#64748b' }}>
                {Math.round((new Date(newRangeEnd).getTime() - new Date(newRangeStart).getTime()) / 86400000) + 1} 天
              </span>
            )}
            <button style={S.addBtn} onClick={addRangeDate}
              disabled={!newRangeStart || !newRangeEnd || newRangeEnd < newRangeStart}>
              + 添加日期段
            </button>
          </div>
        )}
      </div>

      {/* Options + summary */}
      <div style={S.card}>
        <div style={{ display: 'flex', gap: 24, alignItems: 'center', flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: 12, color: '#64748b', marginBottom: 7 }}>舱位</div>
            <div style={{ display: 'flex', gap: 10 }}>
              {Object.entries(CABIN_LABELS).map(([k, v]) => (
                <label key={k} style={{ display: 'flex', alignItems: 'center', gap: 5, cursor: 'pointer', fontSize: 13 }}>
                  <input type="checkbox" checked={!!cabins[k]}
                    onChange={e => setCabins(c => ({ ...c, [k]: e.target.checked }))} />
                  <span style={{ color: cabins[k] ? '#e2e8f0' : '#475569' }}>{v}</span>
                </label>
              ))}
            </div>
          </div>
          <Field label="币种">
            <select style={{ ...S.input, width: 100 }} value={currency} onChange={e => setCurrency(e.target.value)}>
              {CURRENCY_LIST.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </Field>
          <label style={{ display: 'flex', alignItems: 'center', gap: 5, color: '#64748b', fontSize: 13, cursor: 'pointer' }}>
            <input type="checkbox" checked={dryRun} onChange={e => setDryRun(e.target.checked)} />
            演示模式
          </label>
        </div>

        {/* Big summary */}
        <div style={{ marginTop: 14, background: '#0f172a', borderRadius: 8, padding: '12px 16px' }}>
          <div style={{ fontSize: 13, color: '#94a3b8' }}>
            <span style={{ color: '#60a5fa', fontWeight: 600 }}>{routes.length}</span> 条航线
            &nbsp;×&nbsp;
            <span style={{ color: '#60a5fa', fontWeight: 600 }}>{expandedDates.length}</span> 个日期
            &nbsp;×&nbsp;
            <span style={{ color: '#60a5fa', fontWeight: 600 }}>{selectedCabins.length}</span> 个舱位
            &nbsp;=&nbsp;
            <span style={{ color: '#f59e0b', fontWeight: 700, fontSize: 15 }}>{totalQ}</span>
            <span style={{ color: '#475569' }}> 次查询</span>
            <span style={{ color: '#334155', marginLeft: 12, fontSize: 12 }}>
              约 {Math.ceil(totalQ * 0.3)}–{Math.ceil(totalQ * 0.5)} 分钟
            </span>
          </div>
          {totalQ > 50 && (
            <div style={{ marginTop: 6, fontSize: 11, color: '#475569' }}>
              ⚠ 大批量搜索建议在网络稳定时运行，可随时点击"停止"中断
            </div>
          )}
        </div>
      </div>

      {/* Action buttons */}
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        {!running ? (
          <button style={{ ...S.btnPrimary, opacity: (routes.length === 0 || expandedDates.length === 0) ? 0.4 : 1 }}
            disabled={routes.length === 0 || expandedDates.length === 0}
            onClick={runBatch}>
            🔍 开始批量搜索
          </button>
        ) : (
          <button style={{ ...S.btnPrimary, background: '#7f1d1d' }}
            onClick={() => abortRef.current?.abort()}>
            ■ 停止
          </button>
        )}
        {allFlights.length > 0 && !running && (
          <button
            style={{ ...S.btnPrimary, background: 'linear-gradient(135deg,#dc2626,#b91c1c)', opacity: genRep ? 0.6 : 1 }}
            disabled={genRep} onClick={generateReport}>
            {genRep ? '生成中…' : '📊 生成Excel报告'}
          </button>
        )}
        {reportId && (
          <span style={{ color: '#4ade80', fontSize: 13 }}>
            ✓ 报告已下载（ID: {reportId}）
          </span>
        )}
      </div>

      {(running || progress.total > 0) && (
        <ProgressBar current={progress.cur} total={progress.total} message={progress.msg} />
      )}

      {log.length > 0 && (
        <div style={{
          background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8,
          padding: '12px 16px', fontFamily: 'monospace', fontSize: 12,
          color: '#94a3b8', maxHeight: 260, overflowY: 'auto',
        }}>
          {log.map((l, i) => (
            <div key={i} style={{ lineHeight: 1.6, color: l.startsWith('  ✓') ? '#4ade80' : l.startsWith('  ✗') ? '#f87171' : l.startsWith('✅') ? '#4ade80' : '#94a3b8' }}>
              {l}
            </div>
          ))}
        </div>
      )}

      {allFlights.length > 0 && !running && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 12 }}>
          {[
            { label: '航班总数', value: allFlights.length },
            { label: '覆盖航线', value: new Set(allFlights.map(f => `${f.origin}-${f.destination}`)).size },
            { label: '最低价', value: Math.min(...allFlights.map(f => f.price)).toFixed(0) + ' ' + currency },
          ].map(s => (
            <div key={s.label} style={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 10, padding: '16px', textAlign: 'center' }}>
              <div style={{ fontSize: 24, fontWeight: 600, color: '#f8fafc' }}>{s.value}</div>
              <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>{s.label}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

const batchStyles = {
  card: { background: '#1e293b', border: '1px solid #334155', borderRadius: 10, padding: '18px 22px' } as React.CSSProperties,
  sectionHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, marginBottom: 12, flexWrap: 'wrap' as const } as React.CSSProperties,
  cardTitle: { fontSize: 13, fontWeight: 600, color: '#94a3b8', textTransform: 'uppercase' as const, letterSpacing: '0.06em', flexShrink: 0 } as React.CSSProperties,
  dimText: { fontSize: 12, color: '#475569' } as React.CSSProperties,
  input: { background: '#0f172a', border: '1px solid #334155', borderRadius: 6, padding: '7px 11px', color: '#e2e8f0', fontSize: 13, outline: 'none', boxSizing: 'border-box' as const, colorScheme: 'dark' } as React.CSSProperties,
  addBtn: { background: 'linear-gradient(135deg,#3b82f6,#6366f1)', color: 'white', border: 'none', borderRadius: 6, padding: '7px 14px', fontSize: 12, cursor: 'pointer', whiteSpace: 'nowrap' as const } as React.CSSProperties,
  presetBtn: { background: '#0f172a', border: '1px solid #334155', color: '#64748b', borderRadius: 6, padding: '4px 10px', fontSize: 11, cursor: 'pointer', whiteSpace: 'nowrap' as const } as React.CSSProperties,
  btnPrimary: { background: 'linear-gradient(135deg,#3b82f6,#6366f1)', color: 'white', border: 'none', borderRadius: 8, padding: '10px 24px', fontSize: 14, cursor: 'pointer', fontWeight: 500 } as React.CSSProperties,
}

// ── TASK GROUPS SEARCH MODE ───────────────────────────────────────────────────

interface TaskGroupInit {
  groups: Array<{
    origins: string[]
    destinations: string[]
    date_ranges: { start: string; end: string }[]
    specific_dates: string[]
    cabin: string
    label: string
  }>
  currency: string
  datesMode: 'start' | 'endpoints' | 'all'
  title: string
}

type TaskStatus = 'pending' | 'running' | 'done' | 'error' | 'skipped'

interface SearchTask {
  id: string
  groupLabel: string
  origin: string
  destination: string
  dates: string[]
  dateRanges: { start: string; end: string }[]
  cabin: string
  status: TaskStatus
  flightCount: number
  error?: string
}

function expandRange(start: string, end: string): string[] {
  const out: string[] = []
  const cur = new Date(start + 'T00:00:00')
  const last = new Date(end + 'T00:00:00')
  while (cur <= last && out.length < 60) {
    out.push(cur.toISOString().split('T')[0])
    cur.setDate(cur.getDate() + 1)
  }
  return out
}

function expandTaskGroupsToTasks(groups: TaskGroupInit['groups'], datesMode: 'start' | 'endpoints' | 'all'): SearchTask[] {
  const tasks: SearchTask[] = []
  for (const group of groups) {
    let dates: string[]
    if (group.specific_dates.length > 0) {
      dates = group.specific_dates
    } else if (group.date_ranges.length > 0) {
      if (datesMode === 'start') {
        dates = group.date_ranges.map(r => r.start)
      } else if (datesMode === 'endpoints') {
        dates = group.date_ranges.flatMap(r => [r.start, r.end])
      } else {
        // all: every day in each range
        dates = group.date_ranges.flatMap(r => expandRange(r.start, r.end))
      }
    } else {
      dates = []
    }
    for (const origin of group.origins) {
      for (const dest of group.destinations) {
        tasks.push({
          id: uid(),
          groupLabel: group.label || CABIN_LABELS[group.cabin] || group.cabin,
          origin,
          destination: dest,
          dates,
          dateRanges: group.date_ranges,
          cabin: group.cabin,
          status: 'pending',
          flightCount: 0,
        })
      }
    }
  }
  return tasks
}

// How many routes to search at the same time.
// 2 = two browser pages open in parallel → ~2x faster without overwhelming Trip.com.
const PARALLEL_ROUTES = 2

function TaskGroupsSearch({ backendUrl, init }: { backendUrl: string; init: TaskGroupInit }) {
  const initialTasks = expandTaskGroupsToTasks(init.groups, init.datesMode || 'start')
  const [tasks, setTasks] = useState<SearchTask[]>(initialTasks)
  const [running, setRunning] = useState(false)
  const [allFlightsCount, setAllFlightsCount] = useState(0)
  const [reportId, setReportId] = useState<string | null>(null)
  const [genRep, setGenRep] = useState(false)
  const [checkpointId] = useState(`batch-${Date.now().toString(36)}`)
  const allFlightsRef = useRef<FlightResult[]>([])
  const checkpointedRef = useRef(0)   // how many flights already checkpointed
  const abortRef = useRef<AbortController | null>(null)
  // Snapshot of tasks at the start of a run (avoids stale closure in workers)
  const tasksSnapshotRef = useRef<SearchTask[]>(initialTasks)

  const currency = init.currency || 'HKD'
  const title = init.title || '批量搜索任务'
  const doneCount = tasks.filter(t => t.status === 'done').length
  const errorCount = tasks.filter(t => t.status === 'error').length
  const runningCount = tasks.filter(t => t.status === 'running').length

  function updateTask(id: string, patch: Partial<SearchTask>) {
    setTasks(prev => prev.map(t => t.id === id ? { ...t, ...patch } : t))
  }

  // Checkpoint: only save newly added flights since last checkpoint
  async function saveCheckpoint() {
    const all = allFlightsRef.current
    const newFlights = all.slice(checkpointedRef.current)
    if (!newFlights.length) return
    try {
      const allRanges = [...new Map(
        init.groups.flatMap(g => g.date_ranges.map(r => [`${r.start}|${r.end}`, r]))
      ).values()]
      await fetch(`${backendUrl}/api/search/checkpoint`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ checkpoint_id: checkpointId, flights: newFlights, date_ranges: allRanges, title }),
      })
      checkpointedRef.current = all.length
    } catch (e) {
      console.warn('Checkpoint save failed:', e)
    }
  }

  async function runTaskOnce(task: SearchTask): Promise<FlightResult[]> {
    const collected: FlightResult[] = []
    const res = await fetch(`${backendUrl}/api/search/classic`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        origin: task.origin, destination: task.destination,
        dates: task.dates, cabin: task.cabin, currency,
        trip_type: 'one_way', dry_run: false,
        weekday_filter: [], show_browser: false,
      }),
      signal: abortRef.current!.signal,
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const reader = res.body!.getReader()
    const dec = new TextDecoder()
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() ?? ''
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          const evt: SSEEvent = JSON.parse(line.slice(6))
          if (evt.type === 'result' && evt.flights?.length) collected.push(...evt.flights)
        } catch { /* ok */ }
      }
    }
    return collected
  }

  async function startAll() {
    setRunning(true)
    abortRef.current = new AbortController()
    allFlightsRef.current = []
    checkpointedRef.current = 0
    setAllFlightsCount(0)
    setReportId(null)

    // Reset all tasks and take a snapshot for the worker closures
    const snapshot = initialTasks.map(t => ({ ...t, status: 'pending' as TaskStatus, flightCount: 0, error: undefined }))
    tasksSnapshotRef.current = snapshot
    setTasks(snapshot)

    // Shared index across parallel workers (JS is single-threaded so this is safe)
    let nextIdx = 0

    async function worker() {
      while (nextIdx < snapshot.length) {
        if (abortRef.current!.signal.aborted) break
        const i = nextIdx++
        const task = snapshot[i]
        updateTask(task.id, { status: 'running' })

        let flights: FlightResult[] = []
        let success = false

        // Try once, then retry once on failure
        for (let attempt = 0; attempt < 2; attempt++) {
          try {
            flights = await runTaskOnce(task)
            success = true
            break
          } catch (err: any) {
            if (err.name === 'AbortError') {
              updateTask(task.id, { status: 'skipped' })
              return   // exit this worker
            }
            if (attempt === 1) {
              updateTask(task.id, { status: 'error', error: String(err) })
            } else {
              // brief pause before retry
              await new Promise(r => setTimeout(r, 2000))
            }
          }
        }

        if (success) {
          allFlightsRef.current.push(...flights)
          setAllFlightsCount(allFlightsRef.current.length)
          updateTask(task.id, { status: 'done', flightCount: flights.length })
          // Checkpoint after every completed task
          await saveCheckpoint()
        }
      }
    }

    // Launch PARALLEL_ROUTES workers simultaneously
    await Promise.all(Array.from({ length: PARALLEL_ROUTES }, worker))

    // Final checkpoint to catch any stragglers
    await saveCheckpoint()
    setRunning(false)

    // Auto-generate report unless the user manually stopped
    if (!abortRef.current.signal.aborted && allFlightsRef.current.length > 0) {
      await generateReport()
    }
  }

  async function generateReport() {
    if (!allFlightsRef.current.length) return
    setGenRep(true)
    try {
      const allRanges = [...new Map(
        init.groups.flatMap(g => g.date_ranges.map(r => [`${r.start}|${r.end}`, r]))
      ).values()]
      const res = await fetch(`${backendUrl}/api/report/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title,
          flights: allFlightsRef.current,
          date_ranges: allRanges,
          api_key: localStorage.getItem('gemini_api_key') || null,
        }),
      })
      const data = await res.json()
      setReportId(data.report_id)
      window.open(`${backendUrl}/api/report/${data.report_id}/excel`, '_blank')
    } catch (err) {
      console.error('Report gen failed:', err)
    }
    setGenRep(false)
  }

  const statusIcon = (s: TaskStatus) =>
    s === 'done' ? '✓' : s === 'running' ? '⟳' : s === 'error' ? '✗' : s === 'skipped' ? '—' : '·'
  const statusColor = (s: TaskStatus) =>
    s === 'done' ? '#4ade80' : s === 'running' ? '#60a5fa' : s === 'error' ? '#f87171' : '#475569'

  const S = batchStyles

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>

      {/* Header summary */}
      <div style={{ ...S.card, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
        <div>
          <div style={{ fontWeight: 600, color: '#f8fafc', fontSize: 14, marginBottom: 2 }}>{title}</div>
          <div style={{ fontSize: 12, color: '#64748b' }}>
            {tasks.length} 条搜索任务 · {init.groups.length} 个舱位组 ·
            <span style={{ color: '#60a5fa' }}> {PARALLEL_ROUTES}条并行</span> ·
            约 {Math.ceil(tasks.length * 0.5 / PARALLEL_ROUTES)}–{Math.ceil(tasks.length * 0.75 / PARALLEL_ROUTES)} 分钟 ·
            每完成1条自动存档 · ID: <code style={{ color: '#475569', fontSize: 11 }}>{checkpointId.slice(0, 12)}</code>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {!running ? (
            <button style={S.btnPrimary} onClick={startAll} disabled={tasks.length === 0}>
              🚀 开始全部
            </button>
          ) : (
            <button style={{ ...S.btnPrimary, background: '#7f1d1d' }}
              onClick={() => abortRef.current?.abort()}>
              ■ 停止
            </button>
          )}
          {allFlightsRef.current.length > 0 && !running && (
            <button
              style={{ ...S.btnPrimary, background: 'linear-gradient(135deg,#dc2626,#b91c1c)', opacity: genRep ? 0.6 : 1 }}
              disabled={genRep} onClick={generateReport}>
              {genRep ? '生成中…' : '📊 生成报告'}
            </button>
          )}
          {reportId && <span style={{ color: '#4ade80', fontSize: 12 }}>✓ 报告 {reportId}</span>}
        </div>
      </div>

      {/* Progress bar */}
      {(running || doneCount > 0) && (
        <ProgressBar
          current={doneCount + errorCount}
          total={tasks.length}
          message={running
            ? (() => {
                const runningTasks = tasks.filter(t => t.status === 'running')
                const label = runningTasks.map(t => `${t.origin}→${t.destination}`).join(' & ')
                return `[${doneCount + errorCount + runningTasks.length}/${tasks.length}] 搜索中: ${label || '准备中…'}`
              })()
            : `完成 ${doneCount}/${tasks.length}，错误 ${errorCount}，共 ${allFlightsCount} 个航班`}
        />
      )}

      {/* Task status table — compact */}
      <div style={{ ...S.card, padding: '0 0' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 16px 8px', borderBottom: '1px solid #334155' }}>
          <span style={{ fontSize: 12, color: '#64748b', fontWeight: 600 }}>任务列表</span>
          <span style={{ fontSize: 11, color: '#475569' }}>
            ✓ {doneCount} · ✗ {errorCount} · 待执行 {tasks.filter(t => t.status === 'pending').length} · 共 {allFlightsCount} 航班
          </span>
        </div>
        <div style={{ maxHeight: 400, overflowY: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ background: '#0f172a' }}>
                {['#', '航线', '舱位', '日期', '状态', '航班数'].map(h => (
                  <th key={h} style={{ padding: '6px 10px', textAlign: 'left', color: '#475569', fontWeight: 500, whiteSpace: 'nowrap' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {tasks.map((t, i) => (
                <tr key={t.id} style={{
                  borderTop: '1px solid #1e293b',
                  background: t.status === 'running' ? '#0d2240' : 'transparent',
                }}>
                  <td style={{ padding: '5px 10px', color: '#334155' }}>{i + 1}</td>
                  <td style={{ padding: '5px 10px', color: '#e2e8f0', fontWeight: t.status === 'running' ? 600 : 400 }}>
                    {t.origin}→{t.destination}
                  </td>
                  <td style={{ padding: '5px 10px', color: t.cabin === 'Y' ? '#86efac' : '#93c5fd' }}>
                    {CABIN_LABELS[t.cabin] || t.cabin}
                  </td>
                  <td style={{ padding: '5px 10px', color: '#475569' }}>{t.dates.length}天</td>
                  <td style={{ padding: '5px 10px', color: statusColor(t.status), fontWeight: 600 }}>
                    {t.status === 'running' && <span style={{ marginRight: 4 }}>⟳</span>}
                    {statusIcon(t.status)} {t.status === 'running' ? '搜索中' :
                      t.status === 'done' ? '完成' :
                      t.status === 'error' ? '错误' :
                      t.status === 'skipped' ? '跳过' : '待执行'}
                  </td>
                  <td style={{ padding: '5px 10px', color: t.flightCount > 0 ? '#fbbf24' : '#334155' }}>
                    {t.flightCount > 0 ? t.flightCount : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Stats when done */}
      {!running && allFlightsCount > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 10 }}>
          {[
            { label: '航班总数', value: allFlightsCount },
            { label: '完成任务', value: `${doneCount}/${tasks.length}` },
            { label: '覆盖航线', value: new Set(tasks.filter(t => t.status === 'done').map(t => `${t.origin}-${t.destination}`)).size },
            { label: '检查点', value: `每5条 · ${checkpointId.slice(0, 8)}` },
          ].map(s => (
            <div key={s.label} style={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, padding: '12px', textAlign: 'center' }}>
              <div style={{ fontSize: 20, fontWeight: 700, color: '#f8fafc' }}>{s.value}</div>
              <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>{s.label}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Checkpoint recovery ───────────────────────────────────────────────────────

function RecoverFromCheckpoint({ backendUrl }: { backendUrl: string }) {
  const [cpId, setCpId] = useState('')
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState('')

  async function recover() {
    const id = cpId.trim()
    if (!id) return
    setLoading(true)
    setStatus('正在读取检查点…')
    try {
      const cpRes = await fetch(`${backendUrl}/api/search/checkpoint/${id}`)
      if (!cpRes.ok) { setStatus('找不到检查点，请检查 ID'); setLoading(false); return }
      const cp = await cpRes.json()
      if (!cp.flights?.length) { setStatus('检查点中没有航班数据'); setLoading(false); return }

      setStatus(`正在生成报告 (${cp.flights.length} 个航班)…`)
      const repRes = await fetch(`${backendUrl}/api/report/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: cp.title || `检查点 ${id} 报告`,
          flights: cp.flights,
          date_ranges: cp.date_ranges || [],
          api_key: localStorage.getItem('gemini_api_key') || null,
        }),
      })
      const rep = await repRes.json()
      setStatus(`✓ 报告已生成 (ID: ${rep.report_id})`)
      window.open(`${backendUrl}/api/report/${rep.report_id}/excel`, '_blank')
    } catch (e) {
      setStatus(`错误: ${e}`)
    }
    setLoading(false)
  }

  return (
    <div style={{
      background: '#1e293b', border: '1px solid #334155', borderRadius: 8,
      padding: '10px 16px', display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap',
    }}>
      <span style={{ fontSize: 12, color: '#64748b', whiteSpace: 'nowrap' }}>从检查点恢复报告：</span>
      <input
        value={cpId}
        onChange={e => setCpId(e.target.value)}
        onKeyDown={e => e.key === 'Enter' && recover()}
        placeholder="如 batch-moauatgd"
        style={{
          background: '#0f172a', border: '1px solid #334155', borderRadius: 6,
          padding: '5px 10px', color: '#e2e8f0', fontSize: 12, width: 180, outline: 'none',
        }}
      />
      <button
        onClick={recover}
        disabled={!cpId || loading}
        style={{
          background: '#1d4ed8', color: 'white', border: 'none', borderRadius: 6,
          padding: '5px 14px', fontSize: 12, cursor: 'pointer',
          opacity: (!cpId || loading) ? 0.5 : 1,
        }}
      >
        {loading ? '处理中…' : '生成报告'}
      </button>
      {status && (
        <span style={{
          fontSize: 12,
          color: status.startsWith('✓') ? '#4ade80' : status.startsWith('错误') ? '#f87171' : '#94a3b8',
        }}>
          {status}
        </span>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ClassicSearchPage() {
  const { url: backendUrl, status: connStatus } = useBackend()
  const location = useLocation()
  const [mode, setMode] = useState<'batch' | 'single'>('single')
  const [batchInit, setBatchInit] = useState<BatchInit | undefined>(undefined)
  const [singleInit, setSingleInit] = useState<SingleInit | undefined>(undefined)
  const [taskGroupsInit, setTaskGroupsInit] = useState<TaskGroupInit | undefined>(undefined)
  const [initKey, setInitKey] = useState(0)

  // Accept pre-populated config from AI agent navigation
  useEffect(() => {
    const state = location.state as any
    if (state?.taskGroups) {
      setTaskGroupsInit(state.taskGroups)
      setMode('batch')
      setInitKey(k => k + 1)
    } else if (state?.batchSearch) {
      setBatchInit(state.batchSearch)
      setMode('batch')
      setInitKey(k => k + 1)
    } else if (state?.singleSearch) {
      setSingleInit(state.singleSearch)
      setMode('single')
      setInitKey(k => k + 1)
    }
  }, [location.state])

  const S = pageStyles

  // Task groups mode: bypass the tab UI entirely
  if (taskGroupsInit && backendUrl && connStatus === 'connected') {
    return (
      <div style={S.page}>
        <div style={S.header}>
          <span style={{ fontSize: 20 }}>✈️</span>
          <div>
            <h1 style={S.title}>批量任务执行</h1>
            <p style={S.subtitle}>AI规划任务 · 自动检查点 · 完成后生成报告</p>
          </div>
          <button style={{ marginLeft: 'auto', background: 'transparent', border: '1px solid #334155', color: '#64748b', padding: '4px 12px', borderRadius: 6, cursor: 'pointer', fontSize: 12 }}
            onClick={() => setTaskGroupsInit(undefined)}>
            ← 返回手动模式
          </button>
        </div>
        <div style={S.body}>
          <TaskGroupsSearch key={initKey} backendUrl={backendUrl} init={taskGroupsInit} />
          <RecoverFromCheckpoint backendUrl={backendUrl} />
        </div>
      </div>
    )
  }

  return (
    <div style={S.page}>
      <div style={S.header}>
        <span style={{ fontSize: 20 }}>✈️</span>
        <div>
          <h1 style={S.title}>航班价格搜索</h1>
          <p style={S.subtitle}>抓取实时数据 → 生成 Excel 报告 → 自动存入历史数据库</p>
        </div>
        {connStatus === 'connected'
          ? <span style={S.badgeGreen}>后端已连接</span>
          : <span style={S.badgeRed}>后端未连接</span>}
      </div>

      {/* Mode tabs */}
      <div style={S.tabs}>
        {([
          ['single', '🔍 单航线搜索'],
          ['batch',  '📊 批量比价（矩阵报告）'],
        ] as const).map(([m, label]) => (
          <button key={m} style={{ ...S.tab, ...(mode === m ? S.tabActive : {}) }} onClick={() => setMode(m)}>
            {label}
          </button>
        ))}
      </div>

      <div style={S.body}>
        {backendUrl && connStatus === 'connected'
          ? mode === 'single'
            ? <SingleSearch key={initKey} backendUrl={backendUrl} init={singleInit} />
            : <BatchSearch  key={initKey} backendUrl={backendUrl} init={batchInit} />
          : <div style={{ color: '#f87171', padding: 20 }}>后端未连接，请等待或重启应用</div>
        }
        {backendUrl && connStatus === 'connected' && (
          <RecoverFromCheckpoint backendUrl={backendUrl} />
        )}
      </div>
    </div>
  )
}

const pageStyles = {
  page: { minHeight: '100vh', background: '#0f172a', fontFamily: '"PingFang SC","Microsoft YaHei",system-ui,sans-serif', color: '#e2e8f0' } as React.CSSProperties,
  header: { background: '#1e293b', borderBottom: '1px solid #334155', padding: '14px 32px', display: 'flex', alignItems: 'center', gap: 14 } as React.CSSProperties,
  title: { margin: 0, fontSize: 18, fontWeight: 500, color: '#f8fafc' } as React.CSSProperties,
  subtitle: { margin: '2px 0 0', fontSize: 12, color: '#64748b' } as React.CSSProperties,
  badgeGreen: { marginLeft: 'auto', background: '#14532d', color: '#4ade80', padding: '3px 10px', borderRadius: 20, fontSize: 12 } as React.CSSProperties,
  badgeRed: { marginLeft: 'auto', background: '#7f1d1d', color: '#f87171', padding: '3px 10px', borderRadius: 20, fontSize: 12 } as React.CSSProperties,
  tabs: { background: '#1e293b', borderBottom: '1px solid #334155', padding: '0 32px', display: 'flex', gap: 0 } as React.CSSProperties,
  tab: { padding: '12px 20px', fontSize: 13, cursor: 'pointer', background: 'none', border: 'none', color: '#64748b', borderBottom: '2px solid transparent' } as React.CSSProperties,
  tabActive: { color: '#e2e8f0', borderBottomColor: '#3b82f6' } as React.CSSProperties,
  body: { padding: '20px 32px', display: 'flex', flexDirection: 'column', gap: 14 } as React.CSSProperties,
}
