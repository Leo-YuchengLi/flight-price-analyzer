import { useState, useEffect, useCallback } from 'react'
import { useBackend } from '../hooks/useBackend'

interface ReportMeta {
  report_id: string
  title: string
  created_at: string
  total_flights: number
  excel_file: string
  html_file: string
  ai_analysis?: string
  stats: {
    total_flights: number
    total_airlines: number
    price_min: number
    price_avg: number
    direct_pct: number
    ca_index_avg?: number
    currency: string
    date_range: string
  }
}

export default function ReportsPage() {
  const { url: backendUrl, status } = useBackend()
  const [reports, setReports] = useState<ReportMeta[]>([])
  const [loading, setLoading] = useState(false)
  const [preview, setPreview] = useState<{ id: string; url: string } | null>(null)
  const [deleting, setDeleting] = useState<string | null>(null)

  const fetchReports = useCallback(async () => {
    if (!backendUrl || status !== 'connected') return
    setLoading(true)
    try {
      const res = await fetch(`${backendUrl}/api/report/list`)
      setReports(await res.json())
    } catch { /* ignore */ }
    setLoading(false)
  }, [backendUrl, status])

  useEffect(() => { fetchReports() }, [fetchReports])

  async function handleDelete(id: string) {
    if (!backendUrl) return
    setDeleting(id)
    await fetch(`${backendUrl}/api/report/${id}`, { method: 'DELETE' })
    setReports(r => r.filter(x => x.report_id !== id))
    if (preview?.id === id) setPreview(null)
    setDeleting(null)
  }

  function handlePreview(report: ReportMeta) {
    if (preview?.id === report.report_id) {
      setPreview(null)
      return
    }
    setPreview({
      id: report.report_id,
      url: `${backendUrl}/api/report/${report.report_id}/html`,
    })
  }

  function handleDownload(report: ReportMeta) {
    window.open(`${backendUrl}/api/report/${report.report_id}/excel`, '_blank')
  }

  const S = styles

  return (
    <div style={S.page}>
      <div style={S.header}>
        <span style={{ fontSize: 20 }}>📊</span>
        <div>
          <h1 style={S.title}>历史数据库</h1>
          <p style={S.subtitle}>每次搜索完成后自动保存 · 可预览 HTML 或下载 Excel</p>
        </div>
        <button style={{ ...S.btnSecondary, marginLeft: 'auto' }} onClick={fetchReports}>
          刷新
        </button>
      </div>

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Report list */}
        <div style={{
          width: preview ? 380 : '100%',
          borderRight: preview ? '1px solid #1e293b' : 'none',
          overflow: 'auto',
          padding: 24,
          flexShrink: 0,
          transition: 'width 0.2s',
        }}>
          {loading && (
            <p style={{ color: '#475569', textAlign: 'center', marginTop: 40 }}>加载中…</p>
          )}

          {!loading && reports.length === 0 && (
            <div style={{ textAlign: 'center', marginTop: 80, color: '#475569' }}>
              <div style={{ fontSize: 48, marginBottom: 12 }}>📭</div>
              <p style={{ fontSize: 15 }}>暂无报告</p>
              <p style={{ fontSize: 13, marginTop: 6 }}>在经典搜索完成后点击"生成报告"</p>
            </div>
          )}

          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {reports.map(r => (
              <div key={r.report_id} style={{
                ...S.card,
                borderColor: preview?.id === r.report_id ? '#3b82f6' : '#334155',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 14, fontWeight: 500, color: '#e2e8f0', marginBottom: 4 }}
                         title={r.title}>
                      {r.title}
                    </div>
                    <div style={{ fontSize: 11, color: '#475569' }}>{r.created_at}</div>
                  </div>
                </div>

                {/* Stats strip */}
                <div style={{ display: 'flex', gap: 16, margin: '12px 0', flexWrap: 'wrap' }}>
                  {[
                    { v: r.stats.total_flights, l: '航班' },
                    { v: r.stats.total_airlines, l: '航司' },
                    { v: `${r.stats.price_min?.toFixed(0)} ${r.stats.currency}`, l: '最低价' },
                    { v: `${r.stats.direct_pct}%`, l: '直飞' },
                    ...(r.stats.ca_index_avg ? [{ v: r.stats.ca_index_avg, l: '国航指数' }] : []),
                  ].map(stat => (
                    <div key={stat.l} style={{ textAlign: 'center' }}>
                      <div style={{ fontSize: 15, fontWeight: 600, color: '#f8fafc' }}>{stat.v}</div>
                      <div style={{ fontSize: 10, color: '#64748b' }}>{stat.l}</div>
                    </div>
                  ))}
                </div>

                <div style={{ fontSize: 11, color: '#475569', marginBottom: r.ai_analysis ? 8 : 12 }}>
                  {r.stats.date_range}
                </div>

                {/* AI analysis snippet */}
                {r.ai_analysis && (
                  <div style={{
                    background: '#0f172a', border: '1px solid #1e3a6b',
                    borderRadius: 6, padding: '8px 10px', marginBottom: 12,
                    fontSize: 11, color: '#93c5fd', lineHeight: 1.6,
                  }}>
                    🤖 {r.ai_analysis.replace(/<[^>]+>/g, '').slice(0, 120)}…
                  </div>
                )}

                {/* Actions */}
                <div style={{ display: 'flex', gap: 8 }}>
                  <button
                    style={{ ...S.btnPrimary, fontSize: 12, padding: '6px 14px' }}
                    onClick={() => handlePreview(r)}
                  >
                    {preview?.id === r.report_id ? '关闭预览' : '预览 HTML'}
                  </button>
                  <button
                    style={{ ...S.btnGreen, fontSize: 12, padding: '6px 14px' }}
                    onClick={() => handleDownload(r)}
                  >
                    ↓ Excel
                  </button>
                  <button
                    style={{ ...S.btnDanger, fontSize: 12, padding: '6px 14px', opacity: deleting === r.report_id ? 0.5 : 1 }}
                    disabled={deleting === r.report_id}
                    onClick={() => handleDelete(r.report_id)}
                  >
                    删除
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* HTML preview pane */}
        {preview && (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
            <div style={{
              background: '#1e293b', padding: '8px 16px', fontSize: 12,
              color: '#64748b', borderBottom: '1px solid #334155',
              display: 'flex', justifyContent: 'space-between',
            }}>
              <span>预览：{reports.find(r => r.report_id === preview.id)?.title}</span>
              <button
                style={{ background: 'none', border: 'none', color: '#64748b', cursor: 'pointer' }}
                onClick={() => setPreview(null)}
              >✕</button>
            </div>
            <iframe
              key={preview.url}
              src={preview.url}
              style={{ flex: 1, border: 'none', background: 'white' }}
              title="Report preview"
            />
          </div>
        )}
      </div>
    </div>
  )
}

const styles = {
  page: {
    height: '100%', display: 'flex', flexDirection: 'column',
    background: '#0f172a',
    fontFamily: '"PingFang SC","Microsoft YaHei",system-ui,sans-serif',
    color: '#e2e8f0',
  } as React.CSSProperties,
  header: {
    background: '#1e293b', borderBottom: '1px solid #334155',
    padding: '16px 24px', display: 'flex', alignItems: 'center', gap: 12,
  } as React.CSSProperties,
  title: { margin: 0, fontSize: 17, fontWeight: 500, color: '#f8fafc' } as React.CSSProperties,
  subtitle: { margin: '3px 0 0', fontSize: 12, color: '#64748b' } as React.CSSProperties,
  card: {
    background: '#1e293b', border: '1px solid #334155',
    borderRadius: 10, padding: '16px 18px',
  } as React.CSSProperties,
  btnPrimary: {
    background: 'linear-gradient(135deg,#3b82f6,#6366f1)',
    color: 'white', border: 'none', borderRadius: 6, cursor: 'pointer',
  } as React.CSSProperties,
  btnGreen: {
    background: '#14532d', color: '#4ade80',
    border: '1px solid #166534', borderRadius: 6, cursor: 'pointer',
  } as React.CSSProperties,
  btnDanger: {
    background: '#450a0a', color: '#f87171',
    border: '1px solid #7f1d1d', borderRadius: 6, cursor: 'pointer',
  } as React.CSSProperties,
  btnSecondary: {
    background: '#1e293b', color: '#94a3b8',
    border: '1px solid #334155', borderRadius: 6,
    padding: '6px 14px', cursor: 'pointer', fontSize: 13,
  } as React.CSSProperties,
}
