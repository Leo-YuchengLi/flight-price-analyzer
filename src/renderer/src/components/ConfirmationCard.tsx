import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

export interface TaskGroup {
  origins: string[]
  destinations: string[]
  trip_type?: 'one_way' | 'round_trip'
  date_ranges: { start: string; end: string }[]
  specific_dates: string[]
  return_dates?: string[]
  cabin: 'Y' | 'W' | 'C' | 'F'
  label: string
}

export interface SearchIntent {
  reply: string
  clarifying_question: string | null
  origins: string[]
  destinations: string[]
  specific_dates: string[]
  date_ranges: { start: string; end: string }[]
  date_start: string | null
  date_end: string | null
  weekday_filter: number[]
  task_type: 'batch' | 'single'
  trip_type: 'one_way' | 'round_trip'
  return_dates: string[]
  return_date_start: string | null
  return_date_end: string | null
  cabins: string[]
  currency: string
  ready_to_search: boolean
  task_groups: TaskGroup[]
}

interface Props {
  intent: SearchIntent
  onAdjust: () => void
}

const CABIN_LABEL: Record<string, string> = { Y: '经济舱', W: '超级经济舱', C: '商务舱', F: '头等舱' }
const CURRENCY_LIST = ['HKD', 'USD', 'EUR', 'GBP', 'CNY']
const DAY_LABELS = ['一', '二', '三', '四', '五', '六', '日']

function dateRange(start: string | null, end: string | null, weekdayFilter: number[] = []): string[] {
  if (!start) return []
  const dates: string[] = []
  const cur = new Date(start), last = new Date(end || start)
  const days = new Set(weekdayFilter)
  while (cur <= last && dates.length < 60) {
    const d = cur.toISOString().split('T')[0]
    // getDay() returns 0=Sun,...,6=Sat; convert to Mon=0,...,Sun=6
    const wd = (cur.getDay() + 6) % 7
    if (days.size === 0 || days.has(wd)) {
      dates.push(d)
    }
    cur.setDate(cur.getDate() + 1)
  }
  return dates
}

// ── Editable chip list ────────────────────────────────────────────────────────

function ChipList({
  items, onRemove, placeholder, onAdd, inputType = 'text', maxLength = 3,
}: {
  items: string[]
  onRemove: (v: string) => void
  placeholder: string
  onAdd: (v: string) => void
  inputType?: string
  maxLength?: number
}) {
  const [val, setVal] = useState('')
  function submit() {
    const v = val.trim().toUpperCase()
    if (v && !items.includes(v)) { onAdd(v); setVal('') }
  }
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
      {items.map(item => (
        <span key={item} style={S.chip}>
          {item}
          <button style={S.chipX} onClick={() => onRemove(item)}>×</button>
        </span>
      ))}
      <div style={{ display: 'flex', gap: 4 }}>
        <input
          style={S.chipInput}
          value={val}
          onChange={e => setVal(inputType === 'date' ? e.target.value : e.target.value.toUpperCase())}
          onKeyDown={e => e.key === 'Enter' && submit()}
          placeholder={placeholder}
          type={inputType}
          maxLength={maxLength}
        />
        <button style={S.chipAdd} onClick={submit}>+</button>
      </div>
    </div>
  )
}

// ── Task Groups Card (for structured table imports) ───────────────────────────

const CABIN_COLOR: Record<string, { bg: string; text: string }> = {
  Y: { bg: '#1e3a2a', text: '#86efac' },
  C: { bg: '#1e3a6b', text: '#93c5fd' },
  F: { bg: '#3d1a00', text: '#fbbf24' },
}

function TaskGroupsCard({ intent, onAdjust }: Props) {
  const navigate = useNavigate()
  const [filterCabin, setFilterCabin] = useState<string>('all')
  const [selected, setSelected] = useState<boolean[]>(() => intent.task_groups.map(() => true))
  const [currency, setCurrency] = useState('GBP')
  const [datesMode, setDatesMode] = useState<'start' | 'endpoints' | 'all'>('endpoints')

  const groups = intent.task_groups
  const visibleGroups = groups.map((g, i) => ({ ...g, idx: i }))
    .filter(g => filterCabin === 'all' || g.cabin === filterCabin)

  // Count unique cabins
  const cabinCounts = groups.reduce<Record<string, number>>((acc, g) => {
    acc[g.cabin] = (acc[g.cabin] || 0) + g.origins.length * g.destinations.length
    return acc
  }, {})

  // Total tasks estimate
  const selectedGroups = groups.filter((_, i) => selected[i])
  // Compute average days per range for estimate
  const avgRangeLen = groups.length > 0 && groups[0].date_ranges.length > 0
    ? Math.round(groups[0].date_ranges.reduce((s, r) => {
        const d = (new Date(r.end).getTime() - new Date(r.start).getTime()) / 86400000 + 1
        return s + d
      }, 0) / groups[0].date_ranges.length)
    : 7
  const datesPerRange = datesMode === 'start' ? 1 : datesMode === 'endpoints' ? 2 : avgRangeLen
  const totalTasks = selectedGroups.reduce((acc, g) => {
    const routes = g.origins.length * g.destinations.length
    const dates = g.trip_type === 'round_trip'
      ? g.specific_dates.length   // RT: each pair = 1 package search
      : g.date_ranges.length > 0
        ? g.date_ranges.length * datesPerRange
        : g.specific_dates.length
    return acc + routes * dates
  }, 0)

  function toggleGroup(i: number) {
    setSelected(prev => prev.map((v, j) => j === i ? !v : v))
  }

  function launch() {
    const chosenGroups = groups.filter((_, i) => selected[i])
    navigate('/classic', {
      state: {
        taskGroups: {
          groups: chosenGroups,
          currency,
          datesMode,
          title: `AI规划批量搜索 ${new Date().toLocaleDateString('zh-CN')}`,
        }
      }
    })
  }

  return (
    <div style={S.card}>
      <div style={S.header}>
        📋 批量任务计划 <span style={S.badge}>结构化表格</span>
        <span style={{ ...S.badge, background: '#1e3a2a', color: '#86efac', marginLeft: 4 }}>
          {groups.length}组任务 · {totalTasks}次查询
        </span>
      </div>

      {/* Cabin filter */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 10, flexWrap: 'wrap' }}>
        {['all', ...Object.keys(cabinCounts)].map(c => (
          <button key={c} onClick={() => setFilterCabin(c)} style={{
            padding: '4px 12px', fontSize: 11, borderRadius: 20, cursor: 'pointer',
            border: `1px solid ${filterCabin === c ? '#3b82f6' : '#334155'}`,
            background: filterCabin === c ? '#1e40af' : 'transparent',
            color: filterCabin === c ? '#fff' : '#64748b',
          }}>
            {c === 'all' ? `全部 (${groups.length})` :
             c === 'Y' ? `经济舱 (${cabinCounts[c]}条)` :
             c === 'W' ? `超级经济舱 (${cabinCounts[c]}条)` :
             c === 'C' ? `公务舱 (${cabinCounts[c]}条)` : `头等舱 (${cabinCounts[c]}条)`}
          </button>
        ))}
      </div>

      {/* Task group rows */}
      <div style={{ maxHeight: 280, overflow: 'auto', marginBottom: 10 }}>
        {visibleGroups.map(g => {
          const cc = CABIN_COLOR[g.cabin] || CABIN_COLOR.Y
          const routeCount = g.origins.length * g.destinations.length
          const destPreview = g.destinations.slice(0, 6).join(', ') +
            (g.destinations.length > 6 ? ` … +${g.destinations.length - 6}` : '')
          return (
            <div key={g.idx} style={{
              display: 'flex', gap: 8, padding: '8px 10px', marginBottom: 4,
              background: selected[g.idx] ? '#0d2240' : '#0a1525',
              borderRadius: 8, border: `1px solid ${selected[g.idx] ? '#1e4080' : '#1e293b'}`,
              cursor: 'pointer', alignItems: 'flex-start',
            }} onClick={() => toggleGroup(g.idx)}>
              <div style={{
                width: 16, height: 16, borderRadius: 4, flexShrink: 0, marginTop: 2,
                border: `2px solid ${selected[g.idx] ? '#3b82f6' : '#475569'}`,
                background: selected[g.idx] ? '#3b82f6' : 'transparent',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                {selected[g.idx] && <span style={{ color: 'white', fontSize: 10, lineHeight: 1 }}>✓</span>}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
                  <span style={{
                    padding: '1px 8px', borderRadius: 4, fontSize: 11, fontWeight: 600,
                    background: cc.bg, color: cc.text,
                  }}>{CABIN_LABEL[g.cabin]}</span>
                  <span style={{ fontSize: 12, color: '#94a3b8', fontWeight: 600 }}>
                    {g.origins[0]} {g.trip_type === 'round_trip' ? '⇄' : '→'} {routeCount}条航线
                  </span>
                  {g.trip_type === 'round_trip' && (
                    <span style={{ fontSize: 10, color: '#60a5fa', background: '#172554', padding: '1px 6px', borderRadius: 8 }}>往返</span>
                  )}
                </div>
                <div style={{ fontSize: 11, color: '#475569', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {destPreview}
                </div>
                <div style={{ fontSize: 11, color: '#334155', marginTop: 2 }}>
                  {g.trip_type === 'round_trip' && g.specific_dates.length > 0
                    ? `${g.specific_dates.length}个往返日期对：${g.specific_dates.map((d, i) => `${d.slice(5)} ⇄ ${(g.return_dates?.[i] || '').slice(5)}`).join('，')}`
                    : g.date_ranges.length > 0
                      ? `${g.date_ranges.length}个时间段：${g.date_ranges.map(r => `${r.start.slice(5)}~${r.end.slice(5)}`).join('，')}`
                      : `${g.specific_dates.length}个日期：${g.specific_dates.join('，')}`}
                </div>
              </div>
              <div style={{ fontSize: 12, color: '#475569', flexShrink: 0, textAlign: 'right' }}>
                {g.trip_type === 'round_trip'
                  ? routeCount * g.specific_dates.length
                  : routeCount * (g.date_ranges.length > 0 ? g.date_ranges.length * datesPerRange : g.specific_dates.length)}次
              </div>
            </div>
          )
        })}
      </div>

      {/* Options */}
      {/* datesMode selector only for groups with date_ranges (one-way). RT groups use fixed date pairs. */}
      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start', marginBottom: 10, flexWrap: 'wrap' }}>
        {groups.some(g => g.trip_type !== 'round_trip' && g.date_ranges.length > 0) && (
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 11, color: '#64748b', marginBottom: 6 }}>每个时间段搜索哪些日期？</div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {([
              ['start',     `仅第一天`,           `每段只取开始那天（最快）`],
              ['endpoints', `首尾两天`,           `每段取开始和结束各一天`],
              ['all',       `期间每一天`,         `期间内每天都搜索（最全，约${avgRangeLen}倍任务量）`],
            ] as const).map(([m, lbl, tip]) => (
              <button key={m} onClick={() => setDatesMode(m)} title={tip} style={{
                padding: '5px 12px', fontSize: 12, cursor: 'pointer', borderRadius: 6,
                border: `1px solid ${datesMode === m ? '#3b82f6' : '#334155'}`,
                background: datesMode === m ? '#1e40af' : 'transparent',
                color: datesMode === m ? '#fff' : '#94a3b8',
              }}>{lbl}</button>
            ))}
          </div>
          {/* Example */}
          {groups[0]?.date_ranges?.[0] && (
            <div style={{ fontSize: 11, color: '#475569', marginTop: 5 }}>
              例如 {groups[0].date_ranges[groups[0].date_ranges.length - 1].start.slice(5)} ~ {groups[0].date_ranges[groups[0].date_ranges.length - 1].end.slice(5)} 这段，搜索：
              {' '}<span style={{ color: '#93c5fd' }}>
                {datesMode === 'start'
                  ? `仅 ${groups[0].date_ranges[groups[0].date_ranges.length - 1].start.slice(5)}（1天）`
                  : datesMode === 'endpoints'
                  ? `${groups[0].date_ranges[groups[0].date_ranges.length - 1].start.slice(5)} 和 ${groups[0].date_ranges[groups[0].date_ranges.length - 1].end.slice(5)}（2天）`
                  : `${groups[0].date_ranges[groups[0].date_ranges.length - 1].start.slice(5)} 至 ${groups[0].date_ranges[groups[0].date_ranges.length - 1].end.slice(5)} 每一天（${avgRangeLen}天）`}
              </span>
            </div>
          )}
        </div>
        )}
        <div style={{ flexShrink: 0 }}>
          <div style={{ fontSize: 11, color: '#64748b', marginBottom: 6 }}>币种</div>
          <select style={{ ...S.select, width: 80 }} value={currency} onChange={e => setCurrency(e.target.value)}>
            {CURRENCY_LIST.map(c => <option key={c}>{c}</option>)}
          </select>
        </div>
      </div>

      {/* Summary */}
      <div style={S.summary}>
        已选 {selectedGroups.length}/{groups.length} 组 ·
        <strong style={{ color: '#60a5fa', margin: '0 4px' }}>{totalTasks}</strong>次查询 ·
        预计 <strong style={{ color: '#f59e0b' }}>{Math.ceil(totalTasks * 0.5)}–{Math.ceil(totalTasks * 0.75)}</strong> 分钟
        {datesMode === 'all' && totalTasks > 200 && (
          <span style={{ color: '#f59e0b', marginLeft: 6 }}>⚠ 逐日模式任务较多，建议确保网络稳定</span>
        )}
        <span style={{ color: '#475569', marginLeft: 6, fontSize: 11 }}>· 每5条自动存档，中断不丢数据</span>
      </div>

      <div style={{ display: 'flex', gap: 8, marginTop: 14 }}>
        <button
          style={{ ...S.btn, flex: 1, opacity: (selectedGroups.length === 0 || totalTasks === 0) ? 0.5 : 1 }}
          disabled={selectedGroups.length === 0 || totalTasks === 0}
          onClick={launch}
        >
          🚀 开始批量搜索 ({totalTasks}次)
        </button>
        <button style={S.btnGhost} onClick={onAdjust}>继续对话</button>
      </div>
    </div>
  )
}

// ── Main card ─────────────────────────────────────────────────────────────────

export default function ConfirmationCard({ intent, onAdjust }: Props) {
  // Use TaskGroupsCard when AI returned structured table groups
  if (intent.task_groups && intent.task_groups.length > 0) {
    return <TaskGroupsCard intent={intent} onAdjust={onAdjust} />
  }
  const navigate = useNavigate()

  // Defensive override: force batch if multiple destinations or date_ranges present
  const isSingle = intent.task_type === 'single'
    && (intent.destinations?.length || 0) <= 1
    && (intent.date_ranges?.length || 0) === 0

  // Editable state — initialised from AI intent
  const [origins, setOrigins]   = useState(intent.origins)
  const [dests, setDests]       = useState(intent.destinations)
  const [weekdays, setWeekdays] = useState<number[]>(intent.weekday_filter || [])

  // Batch mode: date ranges take priority over specific_dates
  const hasRanges = !isSingle && (intent.date_ranges?.length || 0) > 0
  const [dateRanges, setDateRanges] = useState<{start:string;end:string}[]>(
    intent.date_ranges || []
  )
  const [dates, setDates] = useState(
    !isSingle && !hasRanges
      ? (intent.specific_dates.length > 0
          ? intent.specific_dates
          : dateRange(intent.date_start, intent.date_end, intent.weekday_filter))
      : []
  )

  // Single mode: date range
  // Fallback: if AI used specific_dates instead of date_start/date_end, use those
  const [dateStart, setDateStart] = useState(
    intent.date_start || intent.specific_dates?.[0] || ''
  )
  const [dateEnd, setDateEnd] = useState(
    intent.date_end || intent.specific_dates?.[intent.specific_dates.length - 1] || ''
  )

  const isRoundTrip = intent.trip_type === 'round_trip'
  const [returnDates, setReturnDates] = useState<string[]>(intent.return_dates || [])
  const [returnDateStart, setReturnDateStart] = useState(
    intent.return_date_start || intent.return_dates?.[0] || ''
  )
  const [returnDateEnd, setReturnDateEnd] = useState(
    intent.return_date_end || intent.return_dates?.[intent.return_dates.length - 1] || ''
  )

  const [cabins, setCabins]     = useState<Record<string,boolean>>(
    Object.fromEntries(['Y','W','C','F'].map(c => [c, intent.cabins.includes(c)]))
  )
  const [currency, setCurrency] = useState(intent.currency || 'GBP')
  const [loading, setLoading]   = useState(false)

  const selectedCabins = Object.keys(cabins).filter(k => cabins[k])
  const routes = origins.flatMap(o => dests.map(d => ({ origin: o, destination: d })))

  // For single mode: compute effective dates from range + weekday filter
  const singleDates = isSingle ? dateRange(dateStart, dateEnd, weekdays) : []

  const batchDateCount = hasRanges ? dateRanges.length : dates.length
  const singleReturnDates = isSingle && isRoundTrip
    ? dateRange(returnDateStart, returnDateEnd, weekdays) : []
  const totalQ = isSingle
    ? routes.length * (singleDates.length + (isRoundTrip ? singleReturnDates.length : 0)) * selectedCabins.length
    : routes.length * (batchDateCount + (isRoundTrip ? returnDates.length : 0)) * selectedCabins.length

  function toggleWeekday(wd: number) {
    setWeekdays(prev =>
      prev.includes(wd) ? prev.filter(x => x !== wd) : [...prev, wd].sort()
    )
  }

  function launch() {
    setLoading(true)
    if (isSingle) {
      navigate('/classic', {
        state: {
          singleSearch: {
            origin: origins[0] || '',
            destination: dests[0] || '',
            dateStart,
            dateEnd,
            weekdayFilter: weekdays,
            cabin: selectedCabins[0] || 'Y',
            cabins: selectedCabins,          // pass all selected cabins
            currency,
            tripType: isRoundTrip ? 'round_trip' : 'one_way',
            returnDateStart: isRoundTrip ? returnDateStart : '',
            returnDateEnd: isRoundTrip ? returnDateEnd : '',
          },
        },
      })
    } else {
      navigate('/classic', {
        state: {
          batchSearch: {
            routes,
            dates: hasRanges ? [] : dates,
            dateRanges: hasRanges ? dateRanges : [],
            cabins: selectedCabins,
            currency,
            tripType: isRoundTrip ? 'round_trip' : 'one_way',
            returnDates: isRoundTrip ? returnDates : [],
          },
        },
      })
    }
  }

  const effectiveDates = isSingle ? singleDates : dates
  const datePreview = effectiveDates.length <= 6
    ? effectiveDates.join(', ')
    : `${effectiveDates[0]} … ${effectiveDates[effectiveDates.length - 1]}（共${effectiveDates.length}天）`

  return (
    <div style={S.card}>
      <div style={S.header}>
        ✅ 搜索计划 <span style={S.badge}>可直接编辑</span>
        <span style={{ ...S.badge, marginLeft: 4, background: isSingle ? '#1e3a6b' : '#1e3a2a',
          color: isSingle ? '#93c5fd' : '#86efac' }}>
          {isSingle ? '单线详查' : '批量比价'}
        </span>
      </div>

      {/* Origins */}
      <Row label="出发地" icon="✈">
        <ChipList
          items={origins}
          onRemove={v => setOrigins(o => o.filter(x => x !== v))}
          onAdd={v => setOrigins(o => [...o, v])}
          placeholder="LON"
          maxLength={3}
        />
      </Row>

      {/* Destinations */}
      <Row label="目的地" icon="🛬">
        <ChipList
          items={dests}
          onRemove={v => setDests(d => d.filter(x => x !== v))}
          onAdd={v => setDests(d => [...d, v])}
          placeholder="BJS"
          maxLength={3}
        />
      </Row>

      {/* Dates — batch: chip list (ranges or single); single: range picker */}
      {!isSingle ? (
        hasRanges ? (
          <Row label="日期段" icon="📅">
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {dateRanges.map((r, i) => {
                const days = Math.round((new Date(r.end).getTime() - new Date(r.start).getTime()) / 86400000) + 1
                return (
                  <span key={i} style={S.chip}>
                    {r.start.slice(5)} ~ {r.end.slice(5)} ({days}天)
                    <button style={S.chipX} onClick={() => setDateRanges(prev => prev.filter((_, j) => j !== i))}>×</button>
                  </span>
                )
              })}
              <span style={{ fontSize: 11, color: '#475569', alignSelf: 'center' }}>
                共 {dateRanges.length} 个时间段
              </span>
            </div>
          </Row>
        ) : (
          <Row label="日期" icon="📅">
            <ChipList
              items={dates}
              onRemove={v => setDates(d => d.filter(x => x !== v))}
              onAdd={v => setDates(d => [...d, v].sort())}
              placeholder="2026-06-10"
              inputType="date"
              maxLength={10}
            />
          </Row>
        )
      ) : (
        <>
          <Row label="起始日" icon="📅">
            <input type="date" style={S.dateInput} value={dateStart}
              onChange={e => setDateStart(e.target.value)} />
          </Row>
          <Row label="截止日" icon="📅">
            <input type="date" style={S.dateInput} value={dateEnd}
              onChange={e => setDateEnd(e.target.value)} />
          </Row>
          {/* Weekday filter */}
          <Row label="星期" icon="🗓">
            <div style={{ display: 'flex', gap: 5 }}>
              {DAY_LABELS.map((label, idx) => {
                const active = weekdays.includes(idx)
                return (
                  <button key={idx} onClick={() => toggleWeekday(idx)}
                    style={{
                      ...S.wdBtn,
                      background: active ? '#2563eb' : '#0a1929',
                      color: active ? '#fff' : '#475569',
                      borderColor: active ? '#3b82f6' : '#2a3f5f',
                    }}>
                    {label}
                  </button>
                )
              })}
              {weekdays.length > 0 && (
                <button onClick={() => setWeekdays([])} style={{ ...S.wdBtn, color: '#64748b' }}>
                  清除
                </button>
              )}
            </div>
          </Row>
          {singleDates.length > 0 && (
            <div style={{ fontSize: 11, color: '#64748b', padding: '4px 0 0 26px' }}>
              {datePreview}
            </div>
          )}
        </>
      )}

      {/* Return dates — only for round_trip */}
      {isRoundTrip && (
        !isSingle ? (
          <Row label="返程日" icon="↩️">
            <ChipList
              items={returnDates}
              onRemove={v => setReturnDates(d => d.filter(x => x !== v))}
              onAdd={v => setReturnDates(d => [...d, v].sort())}
              placeholder="2026-07-10"
              inputType="date"
              maxLength={10}
            />
          </Row>
        ) : (
          <>
            <Row label="返程起" icon="↩️">
              <input type="date" style={S.dateInput} value={returnDateStart}
                onChange={e => setReturnDateStart(e.target.value)} />
            </Row>
            <Row label="返程止" icon="↩️">
              <input type="date" style={S.dateInput} value={returnDateEnd}
                onChange={e => setReturnDateEnd(e.target.value)} />
            </Row>
          </>
        )
      )}

      {/* Cabins */}
      <Row label="舱位" icon="💺">
        <div style={{ display: 'flex', gap: 10 }}>
          {['Y','W','C','F'].map(c => (
            <label key={c} style={{ display: 'flex', alignItems: 'center', gap: 5, cursor: 'pointer', fontSize: 13 }}>
              <input type="checkbox" checked={!!cabins[c]}
                onChange={e => setCabins(prev => ({ ...prev, [c]: e.target.checked }))} />
              <span style={{ color: cabins[c] ? '#e2e8f0' : '#475569' }}>{CABIN_LABEL[c]}</span>
            </label>
          ))}
        </div>
      </Row>

      {/* Currency */}
      <Row label="币种" icon="💱">
        <select style={S.select} value={currency} onChange={e => setCurrency(e.target.value)}>
          {CURRENCY_LIST.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
      </Row>

      {/* Summary */}
      <div style={S.summary}>
        {isRoundTrip ? (
          <>
            {routes.length} 条航线 ×（去程 {isSingle ? singleDates.length : (hasRanges ? `${dateRanges.length}段` : dates.length)} + 返程 {isSingle ? singleReturnDates.length : returnDates.length}）个日期 × {selectedCabins.length} 个舱位
            = <strong style={{ color: '#60a5fa' }}>{totalQ} 次查询</strong>
          </>
        ) : (
          <>
            {routes.length} 条航线 × {isSingle ? effectiveDates.length : (hasRanges ? `${dateRanges.length}段` : dates.length)} 个{isSingle || !hasRanges ? '日期' : '时间段'} × {selectedCabins.length} 个舱位
            = <strong style={{ color: '#60a5fa' }}>{totalQ} 次查询</strong>
          </>
        )}
        <span style={{ color: '#475569', marginLeft: 8, fontSize: 11 }}>
          约需 {Math.ceil(totalQ * 0.5)}–{Math.ceil(totalQ)} 分钟
        </span>
      </div>

      {/* Buttons */}
      <div style={{ display: 'flex', gap: 8, marginTop: 14 }}>
        <button
          style={{ ...S.btn, flex: 1, opacity: (loading || totalQ === 0) ? 0.5 : 1 }}
          disabled={loading || totalQ === 0}
          onClick={launch}
        >
          {loading ? '跳转中…' : '🚀 开始搜索'}
        </button>
        <button style={S.btnGhost} onClick={onAdjust}>继续对话</button>
      </div>
    </div>
  )
}

// ── Row helper ────────────────────────────────────────────────────────────────

function Row({ icon, label, children }: { icon: string; label: string; children: React.ReactNode }) {
  return (
    <div style={S.row}>
      <span style={S.rowIcon}>{icon}</span>
      <span style={S.rowLabel}>{label}</span>
      <div style={{ flex: 1 }}>{children}</div>
    </div>
  )
}

// ── Styles ────────────────────────────────────────────────────────────────────

const S = {
  card: {
    background: '#0d1f3c',
    border: '1px solid #1e4080',
    borderRadius: 12,
    padding: '16px 18px',
    maxWidth: 520,
  } as React.CSSProperties,
  header: {
    fontSize: 13, color: '#60a5fa', fontWeight: 600,
    marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8,
  } as React.CSSProperties,
  badge: {
    background: '#1e3a6b', color: '#93c5fd',
    fontSize: 10, padding: '2px 7px', borderRadius: 8,
  } as React.CSSProperties,
  row: {
    display: 'flex', gap: 8, padding: '8px 0',
    borderBottom: '1px solid #1a2d4a',
    alignItems: 'flex-start',
  } as React.CSSProperties,
  rowIcon: { width: 18, flexShrink: 0, marginTop: 2, fontSize: 13 } as React.CSSProperties,
  rowLabel: {
    color: '#4a6fa5', width: 38, flexShrink: 0,
    fontSize: 11, marginTop: 4, letterSpacing: '0.02em',
  } as React.CSSProperties,
  chip: {
    display: 'inline-flex', alignItems: 'center', gap: 3,
    background: '#1a3660', color: '#93c5fd',
    fontSize: 12, padding: '3px 8px', borderRadius: 8,
    border: '1px solid #2a4a80',
  } as React.CSSProperties,
  chipX: {
    background: 'none', border: 'none', cursor: 'pointer',
    color: '#4a6fa5', fontSize: 14, lineHeight: 1,
    padding: '0 0 0 2px',
  } as React.CSSProperties,
  chipInput: {
    background: '#0a1929', border: '1px solid #2a3f5f',
    borderRadius: 6, padding: '3px 8px',
    color: '#e2e8f0', fontSize: 12, outline: 'none', width: 100,
  } as React.CSSProperties,
  chipAdd: {
    background: '#1a3660', border: '1px solid #2a4a80',
    color: '#60a5fa', borderRadius: 6, padding: '3px 8px',
    fontSize: 14, cursor: 'pointer',
  } as React.CSSProperties,
  dateInput: {
    background: '#0a1929', border: '1px solid #2a3f5f',
    borderRadius: 6, padding: '4px 8px',
    color: '#e2e8f0', fontSize: 12, outline: 'none',
  } as React.CSSProperties,
  wdBtn: {
    width: 28, height: 26, border: '1px solid #2a3f5f',
    borderRadius: 5, fontSize: 11, cursor: 'pointer',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
  } as React.CSSProperties,
  select: {
    background: '#0a1929', border: '1px solid #2a3f5f',
    borderRadius: 6, padding: '4px 8px',
    color: '#e2e8f0', fontSize: 12, outline: 'none',
  } as React.CSSProperties,
  summary: {
    fontSize: 12, color: '#64748b', marginTop: 12,
    padding: '8px 10px', background: '#081526', borderRadius: 6,
  } as React.CSSProperties,
  btn: {
    padding: '9px 0',
    background: 'linear-gradient(135deg,#2563eb,#4f46e5)',
    color: 'white', border: 'none', borderRadius: 8,
    fontSize: 13, fontWeight: 500, cursor: 'pointer',
  } as React.CSSProperties,
  btnGhost: {
    padding: '9px 14px', background: 'transparent',
    color: '#64748b', border: '1px solid #334155',
    borderRadius: 8, fontSize: 12, cursor: 'pointer',
  } as React.CSSProperties,
}
