"""
Build the structured CA price-comparison HTML report from ca_analytics output.
Matches the reference format: KPI cards → route tables → warnings → suggestions.
AI is used only for short narrative text (竞争力解读 + 战略建议).
"""
from __future__ import annotations

AIRLINE_LABELS = {
    "CA": "中国国航 ★",
    "CZ": "南方航空",
    "MU": "东方航空",
    "BA": "英国航空",
    "VS": "维珍航空",
    "HU": "海南航空",
}

# Index thresholds for color coding
IDX_HIGH   = 130   # red warning
IDX_MID    = 100   # neutral (CA = market min → green)


def _fmt(v, decimals: int = 0) -> str:
    """Format a number with thousands separator, or return '—' for None."""
    if v is None:
        return "—"
    if decimals == 0:
        return f"{int(round(v)):,}"
    return f"{v:,.{decimals}f}"


def _idx_color(idx: float | None) -> str:
    if idx is None:
        return "#6b7280"
    if idx > IDX_HIGH:
        return "#dc2626"
    if idx > IDX_MID:
        return "#f59e0b"
    return "#16a34a"


def _ca_cell_bg(idx: float | None, ca_p) -> str:
    """Background for the CA price cell."""
    if ca_p is None:
        return "#f9fafb"
    if idx is None:
        return "#ffffff"
    if idx <= 100:
        return "#f0fdf4"   # green — CA is cheapest
    if idx <= 110:
        return "#fefce8"   # yellow — slight premium
    if idx <= 130:
        return "#fff7ed"   # orange — moderate premium
    return "#fff1f2"       # red — high premium


# ── CSS ───────────────────────────────────────────────────────────────────────

CSS = """
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: "PingFang SC","Microsoft YaHei","Noto Sans SC",system-ui,sans-serif;
    background: #f8fafc; color: #1f2937; font-size: 14px; line-height: 1.6;
  }
  .report-wrap { max-width: 1100px; margin: 0 auto; padding: 32px 24px 64px; }

  /* Header */
  .rpt-header { margin-bottom: 24px; }
  .rpt-header h1 { font-size: 24px; color: #1e40af; margin-bottom: 6px; }
  .rpt-header .sub { font-size: 12px; color: #6b7280; }

  /* Cabin tabs */
  .cabin-tabs { display: flex; gap: 0; margin-bottom: 20px; border-bottom: 2px solid #e5e7eb; }
  .cabin-tab {
    padding: 10px 24px; cursor: pointer; font-size: 14px; font-weight: 500;
    color: #6b7280; border-bottom: 2px solid transparent; margin-bottom: -2px;
    transition: all 0.15s;
  }
  .cabin-tab.active { color: #1e40af; border-bottom-color: #1e40af; }

  /* KPI cards */
  .kpi-row { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 20px; }
  .kpi-card {
    flex: 1; min-width: 130px; background: white; border-radius: 10px;
    padding: 16px 14px; text-align: center;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06); border: 1px solid #e5e7eb;
  }
  .kpi-value { font-size: 28px; font-weight: 700; margin-bottom: 4px; }
  .kpi-label { font-size: 11px; color: #6b7280; }

  /* Section */
  .section { background: white; border-radius: 10px; padding: 20px 22px; margin-bottom: 16px;
             box-shadow: 0 1px 4px rgba(0,0,0,0.06); border: 1px solid #e5e7eb; }
  .section-title {
    font-size: 15px; font-weight: 600; color: #1e40af; margin-bottom: 14px;
    padding-bottom: 8px; border-bottom: 2px solid #dbeafe;
    display: flex; align-items: center; gap: 6px;
  }

  /* Cabin content */
  .cabin-content { display: none; }
  .cabin-content.active { display: block; }

  /* Route block */
  .route-block { margin-bottom: 22px; }
  .route-label {
    font-size: 14px; font-weight: 700; color: #1e40af; margin-bottom: 8px;
    display: flex; align-items: center; gap: 8px;
  }
  .type-badge {
    font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 4px;
    background: #dbeafe; color: #1e40af;
  }

  /* Price table */
  .price-table { width: 100%; border-collapse: collapse; font-size: 13px; }
  .price-table th {
    background: #1e40af; color: white; padding: 9px 10px; text-align: center;
    font-weight: 500; white-space: nowrap;
  }
  .price-table th:first-child { text-align: left; }
  .price-table td {
    padding: 8px 10px; text-align: center; border-bottom: 1px solid #f3f4f6;
  }
  .price-table td:first-child { text-align: left; color: #374151; font-size: 12px; }
  .price-table tr:hover td { background: #f9fafb !important; }
  .price-table tr:last-child td { border-bottom: none; }

  /* Warning / opportunity sections */
  .warn-list { list-style: none; }
  .warn-list li { padding: 7px 0; border-bottom: 1px solid #f3f4f6; font-size: 13px; }
  .warn-list li:last-child { border-bottom: none; }
  .warn-tag { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; margin-right: 6px; }
  .warn-red  { background: #fee2e2; color: #dc2626; }
  .warn-green{ background: #dcfce7; color: #16a34a; }

  /* Collapsible sections */
  .collapsible summary { cursor: pointer; font-size: 14px; font-weight: 500; color: #374151; padding: 10px 0; }
  .collapsible summary:hover { color: #1e40af; }
  .method-item { margin: 8px 0 12px 0; font-size: 13px; color: #4b5563; }
  .method-item strong { color: #1e40af; }

  /* Print */
  @media print { body { background: white; } .cabin-tabs { display: none; } .cabin-content { display: block !important; } }
</style>

<script>
function switchCabin(cabinCode) {
  document.querySelectorAll('.cabin-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.cabin-content').forEach(c => c.classList.remove('active'));
  document.querySelector('[data-cabin="' + cabinCode + '"]').classList.add('active');
  document.getElementById('cabin-' + cabinCode).classList.add('active');
}
</script>
"""


# ── Route table ───────────────────────────────────────────────────────────────

def _route_table(route_data: dict, currency: str) -> str:
    route = route_data["route"]
    typ   = route_data["type"]
    periods = route_data["periods"]

    rows = []
    for p in periods:
        ca_p   = p.get("ca")
        cz_p   = p.get("cz")
        mu_p   = p.get("mu")
        ba_vs  = p.get("ba_vs")
        ba_nm  = p.get("ba_vs_name", "")
        hu_p   = p.get("hu")
        mmin   = p.get("market_min")
        mair   = p.get("market_min_airline", "")
        idx    = p.get("ca_index")
        vs_min = p.get("ca_vs_min")
        period = p.get("period", "")

        # CA cell styling
        ca_bg    = _ca_cell_bg(idx, ca_p)
        ca_color = _idx_color(idx) if ca_p is not None else "#9ca3af"
        ca_bold  = "font-weight:700;" if ca_p is not None else ""

        # vs_min cell
        if vs_min is None:
            vs_min_html = "<span style='color:#9ca3af'>—</span>"
        elif vs_min == 0:
            vs_min_html = "<span style='color:#16a34a;font-weight:700'>持平</span>"
        else:
            sign = "+" if vs_min > 0 else ""
            col  = "#dc2626" if vs_min > 0 else "#16a34a"
            vs_min_html = f"<span style='color:{col};font-weight:600'>{sign}{_fmt(vs_min)}</span>"

        # index cell
        if idx is None:
            idx_html = "<span style='color:#9ca3af'>—</span>"
        else:
            col = _idx_color(idx)
            idx_html = f"<span style='color:{col};font-weight:600'>{idx}</span>"

        # market_min cell
        if mmin is None:
            mmin_html = "—"
        else:
            mmin_html = f"<span style='color:#16a34a;font-weight:600'>{mair} {_fmt(mmin)}</span>"

        # BA/VS cell with name label
        if ba_vs is not None:
            ba_label = f"<span style='font-size:10px;color:#6b7280'>({ba_nm})</span>"
            ba_html  = f"{_fmt(ba_vs)} {ba_label}"
        else:
            ba_html = "—"

        rows.append(f"""
        <tr>
          <td>{period}</td>
          <td style="background:{ca_bg};{ca_bold}color:{ca_color}">{_fmt(ca_p)}</td>
          <td>{_fmt(cz_p)}</td>
          <td>{_fmt(mu_p)}</td>
          <td>{ba_html}</td>
          <td>{_fmt(hu_p)}</td>
          <td style="background:#f0fdf4">{mmin_html}</td>
          <td>{vs_min_html}</td>
          <td>{idx_html}</td>
        </tr>""")

    rows_html = "\n".join(rows)
    return f"""
<div class="route-block">
  <div class="route-label">
    航线: {route}
    <span class="type-badge">{typ}</span>
  </div>
  <table class="price-table">
    <thead>
      <tr>
        <th>日期</th>
        <th>中国国航 ★</th>
        <th>南方航空</th>
        <th>东方航空</th>
        <th>英国航空/维珍</th>
        <th>海南航空</th>
        <th>最低价(航司+价格)</th>
        <th>国航vs最低价</th>
        <th>指数</th>
      </tr>
    </thead>
    <tbody>
      {rows_html}
    </tbody>
  </table>
</div>"""


# ── Warnings & opportunities ──────────────────────────────────────────────────

def _coverage_section(cov: dict) -> str:
    """Data coverage summary + market gaps (routes without CA data)."""
    if not cov:
        return ""

    total_f = cov.get("total_flights", 0)
    tt      = cov.get("trip_type_counts", {})
    ow      = tt.get("one_way", 0)
    rt      = tt.get("round_trip", 0)
    direct  = cov.get("direct_count", 0)
    conn    = cov.get("connecting_count", 0)
    n_total = cov.get("total_routes", 0)
    n_ca    = cov.get("ca_routes_count", 0)
    no_ca   = cov.get("routes_without_ca", [])

    # Mixed data warning
    mixed_warn = ""
    if ow > 0 and rt > 0:
        mixed_warn = (
            f'<p style="margin:8px 0;color:#b45309;background:#fef3c7;'
            f'padding:8px 12px;border-radius:6px;font-size:12.5px">'
            f'⚠ <strong>数据混合警告：</strong>本报告包含单程（{ow}条）和往返（{rt}条）票价。'
            f'往返价格为来回打包价，<strong>不应与单程价格直接比较</strong>。'
            f'建议分别对单程和往返数据生成独立报告以获得准确分析。</p>'
        )

    # Market gap: routes without CA data
    gap_html = ""
    if no_ca:
        lis = "".join(
            f'<li style="display:inline-block;margin:3px 6px 3px 0;padding:3px 10px;'
            f'background:#f0f9ff;border:1px solid #bae6fd;border-radius:12px;font-size:12px">'
            f'{r}</li>'
            for r in no_ca[:20]
        )
        gap_html = f"""
<h3 style="color:#0369a1;font-size:14px;margin:14px 0 8px">🔵 市场机会（无国航报价航线）</h3>
<p style="font-size:12px;color:#6b7280;margin-bottom:6px">
  以下 {len(no_ca)} 条航线有竞争对手数据但国航未出现，可能是潜在布局或加班机会：
</p>
<ul style="list-style:none;padding:0">{lis}</ul>"""

    return f"""
<div class="section">
  <div class="section-title">📊 数据覆盖概况</div>
  <div style="display:flex;gap:24px;flex-wrap:wrap;margin-bottom:12px">
    <div style="font-size:13px;color:#374151">
      <strong>总记录：</strong>{total_f} 条 &nbsp;|&nbsp;
      <strong>单程：</strong>{ow} &nbsp;/&nbsp; <strong>往返：</strong>{rt}
    </div>
    <div style="font-size:13px;color:#374151">
      <strong>直飞：</strong>{direct} 条 &nbsp;|&nbsp; <strong>中转：</strong>{conn} 条
    </div>
    <div style="font-size:13px;color:#374151">
      <strong>航线覆盖：</strong>{n_total} 条，国航有报价 {n_ca} 条
      {"，<span style='color:#dc2626'>" + str(len(no_ca)) + " 条无国航数据</span>" if no_ca else ""}
    </div>
  </div>
  {mixed_warn}
  {gap_html}
</div>"""


def _warnings_section(cabins: dict, currency: str) -> str:
    high_items, low_items, missing = [], [], 0

    for cabin_code, cd in cabins.items():
        cabin_label = cd.get("label", cabin_code)
        missing += cd.get("ca_missing_count", 0)
        for route in cd.get("routes", []):
            for p in route.get("periods", []):
                idx  = p.get("ca_index")
                ca_p = p.get("ca")
                mmin = p.get("market_min")
                mair = p.get("market_min_airline", "")
                vs_m = p.get("ca_vs_min")
                per  = p.get("period", "")

                if idx and idx > IDX_HIGH and ca_p and mmin:
                    high_items.append((idx, cabin_label, route["route"], per, ca_p, mair, mmin, vs_m))
                if vs_m == 0 and ca_p is not None:
                    low_items.append((cabin_label, route["route"], per, ca_p))

    # Sort by index desc
    high_items.sort(key=lambda x: -x[0])

    high_html = ""
    if high_items:
        lis = []
        for (idx, cl, rt, per, ca_p, mair, mmin, vs_m) in high_items[:12]:
            sign = f"+{_fmt(vs_m)}" if vs_m else "—"
            lis.append(
                f"<li><span class='warn-tag warn-red'>⚠ {cl}</span>"
                f"<strong>{rt}</strong> ({per}): "
                f"国航 {_fmt(ca_p)} vs {mair} {_fmt(mmin)}，溢价 {sign}"
                f"（指数 <span style='color:#dc2626;font-weight:700'>{idx}</span>）</li>"
            )
        high_html = f"""
<h3 style="color:#dc2626;font-size:14px;margin:12px 0 8px">🔴 高溢价预警（指数 &gt; {IDX_HIGH}）</h3>
<p style="font-size:12px;color:#6b7280;margin-bottom:8px">以下航线×日期国航价格显著高于市场最低价，建议考虑调价：</p>
<ul class="warn-list">{''.join(lis)}</ul>"""

    low_html = ""
    if low_items:
        lis = []
        for (cl, rt, per, ca_p) in low_items[:12]:
            lis.append(
                f"<li><span class='warn-tag warn-green'>✓ {cl}</span>"
                f"<strong>{rt}</strong> ({per}): "
                f"国航 {_fmt(ca_p)}，为市场最低价</li>"
            )
        low_html = f"""
<h3 style="color:#16a34a;font-size:14px;margin:16px 0 8px">🟢 价格竞争力强的航线</h3>
<p style="font-size:12px;color:#6b7280;margin-bottom:8px">以下航线×日期国航提供市场最低价，可考虑维持或适当提价：</p>
<ul class="warn-list">{''.join(lis)}</ul>"""

    missing_html = ""
    if missing:
        missing_html = f"""
<h3 style="color:#f59e0b;font-size:14px;margin:16px 0 8px">🟡 国航数据缺失</h3>
<p style="font-size:13px;color:#4b5563">
  有 <strong>{missing}</strong> 个舱位×航线×日期组合中未找到国航价格数据，建议检查航线覆盖或数据采集完整性。
</p>"""

    return f"""
<div class="section">
  <div class="section-title">💡 价格决策建议</div>
  {high_html}
  {low_html}
  {missing_html}
</div>"""


# ── Methodology section ───────────────────────────────────────────────────────

METHODOLOGY_HTML = """
<div class="section">
  <details class="collapsible">
    <summary>🎓 更专业的分析方法建议 ▾</summary>
    <div style="margin-top:12px">
      <div class="method-item"><strong>1. 价格弹性分析 (Price Elasticity)</strong><br>
      量化价格变动对需求的影响。建议收集各航司客座率/预订量数据，与价格变动关联，计算需求价格弹性系数。若 |E| &gt; 1（弹性需求），降价可增加总收入；若 |E| &lt; 1（非弹性需求），可适度提价。</div>
      <div class="method-item"><strong>2. 动态定价基准线 (Dynamic Pricing Benchmark)</strong><br>
      建立时间序列价格曲线：同一航线在出发前 60/30/14/7 天的价格变化趋势，分析竞对的定价节奏，据此制定国航的动态调价时间窗口。</div>
      <div class="method-item"><strong>3. 价格带分析 (Price Band Analysis)</strong><br>
      对每条航线计算价格分布的 P25/P50/P75，而非仅看最低价。国航定价在 P25 以下为激进策略，P50-P75 为价值策略，P75 以上为高端策略。</div>
      <div class="method-item"><strong>4. 竞争反应博弈模型 (Game-Theoretic Pricing)</strong><br>
      航空定价本质是寡头博弈。若国航降价，竞对是否跟随？对英国航空和维珍航空等外航，可分析其历史调价反应模式。</div>
      <div class="method-item"><strong>5. 收益管理指标 (Revenue Management KPIs)</strong><br>
      引入 RASK、客座率、收益 per ASK 等行业标准指标。低价格高客座率 ≠ 最优收益，需将价格对比与实际客座率数据结合。</div>
    </div>
  </details>
</div>

<div class="section">
  <details class="collapsible">
    <summary>📝 方法论说明 ▾</summary>
    <div style="margin-top:12px;font-size:13px;color:#4b5563">
      <p style="margin-bottom:6px">• <strong>数据筛选：</strong>仅保留直飞与经停1次的航班，剔除2次及以上中转</p>
      <p style="margin-bottom:6px">• <strong>舱等区分：</strong>按舱位分为经济舱/公务舱独立分析，不跨舱等混合比较</p>
      <p style="margin-bottom:6px">• <strong>最低价规则：</strong>同一航司、同一航线、同一日期、同一舱等，取最低票价</p>
      <p style="margin-bottom:6px">• <strong>价格指数：</strong>国航价格 / 市场最低价 × 100。100 = 与最低价持平；&gt;100 = 溢价</p>
      <p style="margin-bottom:6px">• <strong>竞对均价：</strong>排除国航后，其余在场航司价格的算术平均值</p>
      <p>• <strong>航线分类：</strong>DIRECT = 直达；ID = 国际出发→国内目的地；II = 国际出发→国际目的地</p>
    </div>
  </details>
</div>"""


# ── Main builder ──────────────────────────────────────────────────────────────

def build_analysis_html(
    analytics: dict,
    title: str,
    ai_narratives: dict[str, str] | None = None,
    ai_recommendations: str | None = None,
) -> str:
    """
    Build the full HTML report.

    analytics       : output of compute_ca_analytics()
    title           : report title
    ai_narratives   : {cabin_code: "narrative text"} for 竞争力解读 per cabin
    ai_recommendations: HTML string for strategic recommendations section
    """
    currency = analytics.get("currency", "GBP")
    cabins   = analytics.get("cabins", {})
    cov      = analytics.get("coverage", {})

    # ── Cabin tabs ────────────────────────────────────────────────────────────
    first_cabin  = next(iter(cabins), None)
    tab_items    = []
    content_items = []

    for cabin_code, cd in cabins.items():
        label      = cd.get("label", cabin_code)
        total      = cd.get("total_combos", 0)
        active_cls = "active" if cabin_code == first_cabin else ""

        tab_items.append(
            f'<div class="cabin-tab {active_cls}" data-cabin="{cabin_code}" '
            f'onclick="switchCabin(\'{cabin_code}\')">'
            f'{label} ({total}组)</div>'
        )

        # ── KPI cards ─────────────────────────────────────────────────────
        ca_avg_idx = cd.get("ca_avg_index")
        kpi_cards = [
            (_fmt(total),                        "航线×日期组合", "#1e40af"),
            (_fmt(cd.get("ca_cheapest_count",0)), "国航最低价次数", "#dc2626"),
            (_fmt(cd.get("ca_below_avg_count",0)),"国航低于竞对均价", "#16a34a"),
            (_fmt(cd.get("ca_above_avg_count",0)),"国航高于竞对均价", "#f59e0b"),
            (f"{ca_avg_idx}" if ca_avg_idx else "—", "国航平均价格指数",
             _idx_color(ca_avg_idx)),
            (f"{cd.get('ca_below_avg_pct',0)}%",  "国航低于竞对均价占比", "#6366f1"),
        ]
        kpi_html = "".join(
            f'<div class="kpi-card">'
            f'<div class="kpi-value" style="color:{color}">{val}</div>'
            f'<div class="kpi-label">{lbl}</div>'
            f'</div>'
            for val, lbl, color in kpi_cards
        )

        # ── 竞争力解读 ────────────────────────────────────────────────────
        if ai_narratives and cabin_code in ai_narratives:
            narrative = ai_narratives[cabin_code]
        else:
            # Auto-generated fallback
            idx_v = ca_avg_idx or 0
            pct   = cd.get("ca_below_avg_pct", 0)
            chp   = cd.get("ca_cheapest_count", 0)
            tot   = total or 1
            if idx_v > 120:
                tone = f"国航整体价格指数为 <strong>{ca_avg_idx}</strong>，显著高于市场最低价（溢价{round(idx_v-100,1)}%），<span style='background:#fee2e2;color:#dc2626;padding:1px 6px;border-radius:4px;font-size:12px'>价格竞争力不足</span>。"
            elif idx_v > 105:
                tone = f"国航整体价格指数为 <strong>{ca_avg_idx}</strong>，略高于市场最低价（溢价{round(idx_v-100,1)}%），价格处于中等偏高水平。"
            else:
                tone = f"国航整体价格指数为 <strong>{ca_avg_idx}</strong>，价格具备一定竞争力。"
            narrative = (
                f"{label} — {tone}<br>"
                f"在 {total} 个航线×日期组合中，国航有 <strong>{chp}</strong> 次（{round(chp/tot*100,1)}%）提供市场最低价。"
            )

        narrative_html = f"""
<div class="section">
  <div class="section-title">📋 竞争力解读</div>
  <p style="font-size:13.5px;line-height:1.9;color:#374151">{narrative}</p>
</div>"""

        # ── Route tables ──────────────────────────────────────────────────
        routes_html = "".join(_route_table(r, currency) for r in cd.get("routes", []))

        routes_section = f"""
<div class="section">
  <div class="section-title">🗺️ 按航线价格对比</div>
  {routes_html}
</div>"""

        content_items.append(f"""
<div id="cabin-{cabin_code}" class="cabin-content {active_cls}">
  <div class="kpi-row">{kpi_html}</div>
  {narrative_html}
  {routes_section}
</div>""")

    tabs_html    = "\n".join(tab_items)
    content_html = "\n".join(content_items)

    # ── AI strategic recommendations ──────────────────────────────────────
    reco_section = ""
    if ai_recommendations:
        reco_section = f"""
<div class="section">
  <div class="section-title">🚀 战略建议</div>
  <div style="font-size:13.5px;line-height:1.9;color:#374151">{ai_recommendations}</div>
</div>"""

    # ── Assemble ──────────────────────────────────────────────────────────
    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{title}</title>
  {CSS}
</head>
<body>
<div class="report-wrap">

  <div class="rpt-header">
    <h1>✈️ {title}</h1>
    <div class="sub">
      中国国航视角 · 币种 {currency} · 仅含直飞与经停1次 · 按舱等分区分析
      {"· <span style='color:#b45309'>⚠ 含往返+单程混合数据</span>" if cov.get("trip_type_counts", {}).get("round_trip", 0) > 0 and cov.get("trip_type_counts", {}).get("one_way", 0) > 0 else ""}
    </div>
  </div>

  <div class="cabin-tabs">{tabs_html}</div>
  {content_html}

  {_warnings_section(cabins, currency)}
  {_coverage_section(cov)}
  {reco_section}
  {METHODOLOGY_HTML}

</div>
</body>
</html>"""
