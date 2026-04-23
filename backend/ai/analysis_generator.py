"""
Gemini AI — generates only narrative text sections for the analysis report.
The structured tables/KPIs are built programmatically by analysis_html_builder.py.
"""
from __future__ import annotations

import os
import re
from typing import AsyncGenerator

from dotenv import load_dotenv
from google import genai
from google.genai import types

from report.ca_analytics import compute_ca_analytics
from report.analysis_html_builder import build_analysis_html

load_dotenv()


# ── Prompts ───────────────────────────────────────────────────────────────────

NARRATIVE_PROMPT = """你是国航（Air China）商务/收益管理分析师。
根据以下数据，为"{label}"舱位写一段竞争力解读（约80-120字，中文，不要用markdown）。
要求：
- 提及平均价格指数、低于均价占比、高溢价问题或优势
- 语言专业简洁，直接给出判断
- 输出纯文本，不含标题

数据：
- 总组合数: {total_combos}
- 国航最低价次数: {ca_cheapest}（占比{ca_cheapest_pct}%）
- 国航低于竞对均价次数: {ca_below}（{ca_below_pct}%）
- 国航平均价格指数: {ca_avg_index}（100=市场最低价）
- 高溢价预警（指数>130）: {high_count}处
"""

RECOMMENDATIONS_PROMPT = """你是国航（Air China）收益管理顾问。
根据以下竞争力数据，写一份简洁的战略建议（约200-300字，中文，HTML格式）。

格式：用<p>分段，关键词用<strong>，建议项用有序列表<ol><li>，不超过5条建议。
不要用markdown，不要输出说明文字，直接输出HTML片段。

数据摘要：
{summary}
"""

CHAT_SYSTEM = """你是一位国际航空票价分析师助手，基于已生成的竞争力分析报告回答问题。
要求：
- 中文回答，专业简洁
- 引用报告中的具体数字
- 如报告无相关数据，如实说明

报告内容摘要（前5000字）：
{report_summary}"""


# ── Client ────────────────────────────────────────────────────────────────────

def _make_client(api_key: str | None = None) -> genai.Client:
    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise ValueError("GEMINI_API_KEY not set")
    return genai.Client(api_key=key)


def _build_summary(analytics: dict) -> str:
    """Compact text summary for recommendations prompt."""
    lines = [f"币种: {analytics.get('currency', 'HKD')}"]
    for code, cd in analytics.get("cabins", {}).items():
        label = cd.get("label", code)
        total = cd.get("total_combos", 0)
        idx   = cd.get("ca_avg_index", 0) or 0
        below = cd.get("ca_below_avg_pct", 0)
        chp   = cd.get("ca_cheapest_count", 0)
        hi    = sum(
            1 for r in cd.get("routes", [])
            for p in r.get("periods", [])
            if (p.get("ca_index") or 0) > 130
        )
        lines.append(
            f"{label}: 组合{total}个, 平均指数{idx}, "
            f"低于均价{below}%, 最低价{chp}次, 高溢价{hi}处"
        )
        # Top high-premium routes
        highs = sorted(
            [(p.get("ca_index", 0), r["route"], p.get("period",""), p.get("ca"), p.get("market_min"), p.get("market_min_airline",""))
             for r in cd.get("routes", []) for p in r.get("periods", []) if (p.get("ca_index") or 0) > 130],
            reverse=True,
        )[:5]
        for (i, rt, per, ca_p, mm, ma) in highs:
            lines.append(f"  ⚠ {rt} {per}: CA={ca_p}, 最低={mm}({ma}), 指数={i}")
    return "\n".join(lines)


# ── Public API ────────────────────────────────────────────────────────────────

async def generate_outline(
    flights: list[dict],
    title: str,
    date_ranges: list[dict] | None = None,
    api_key: str | None = None,
) -> str:
    """Return a brief outline (just lists the main sections that will be generated)."""
    analytics = compute_ca_analytics(flights, date_ranges=date_ranges)
    cabins    = analytics.get("cabins", {})
    lines = [
        f"# {title}",
        "",
        "## 报告结构",
        "",
    ]
    for code, cd in cabins.items():
        label = cd.get("label", code)
        total = cd.get("total_combos", 0)
        idx   = cd.get("ca_avg_index", 0) or 0
        hi    = sum(1 for r in cd.get("routes", []) for p in r.get("periods", []) if (p.get("ca_index") or 0) > 130)
        lines.append(f"### {label}（{total}组）")
        lines.append(f"- 平均价格指数: {idx}，高溢价预警: {hi}处")
        lines.append(f"- 航线数: {len(cd.get('routes', []))}")
        lines.append("")

    route_count = sum(len(cd.get("routes", [])) for cd in cabins.values())
    lines += [
        "## 报告包含以下章节",
        f"1. KPI 总览卡片（各舱位）",
        f"2. 竞争力解读（AI 生成）",
        f"3. 按航线价格对比表（{route_count} 条航线，含颜色编码）",
        f"4. 高溢价预警 & 价格竞争力强的航线",
        f"5. AI 战略建议",
        f"6. 更专业的分析方法 & 方法论说明",
        "",
        "---",
        "报告将以结构化 HTML 格式生成，表格含颜色编码，可直接下载查阅。",
        '确认后点击【确认大纲，开始生成】即可生成完整报告。',
    ]
    return "\n".join(lines)


async def generate_report_stream(
    flights: list[dict],
    title: str,
    outline: str,
    date_ranges: list[dict] | None = None,
    api_key: str | None = None,
) -> AsyncGenerator[str, None]:
    """
    Build the structured HTML report programmatically, then add AI narrative.
    Yields text chunks: first the base HTML structure, then AI-enhanced sections.
    """
    client   = _make_client(api_key)
    analytics = compute_ca_analytics(flights, date_ranges=date_ranges)
    cabins    = analytics.get("cabins", {})

    # ── Step 1: Generate AI narratives per cabin ──────────────────────────────
    ai_narratives: dict[str, str] = {}
    for cabin_code, cd in cabins.items():
        label = cd.get("label", cabin_code)
        total = cd.get("total_combos", 0)
        idx   = cd.get("ca_avg_index", 0) or 0
        below = cd.get("ca_below_avg_pct", 0)
        chp   = cd.get("ca_cheapest_count", 0)
        hi    = sum(1 for r in cd.get("routes", []) for p in r.get("periods", []) if (p.get("ca_index") or 0) > 130)
        pct_chp = round(chp / max(total, 1) * 100, 1)

        prompt = NARRATIVE_PROMPT.format(
            label=label, total_combos=total, ca_cheapest=chp,
            ca_cheapest_pct=pct_chp, ca_below=cd.get("ca_below_avg_count", 0),
            ca_below_pct=below, ca_avg_index=idx, high_count=hi,
        )
        try:
            resp = await client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=[{"role": "user", "parts": [{"text": prompt}]}],
                config=types.GenerateContentConfig(temperature=0.3),
            )
            ai_narratives[cabin_code] = resp.text.strip()
        except Exception:
            pass  # fallback to auto-generated text in builder

    # ── Step 2: Generate AI strategic recommendations ─────────────────────────
    ai_reco: str | None = None
    try:
        summary = _build_summary(analytics)
        reco_prompt = RECOMMENDATIONS_PROMPT.format(summary=summary)
        resp = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=[{"role": "user", "parts": [{"text": reco_prompt}]}],
            config=types.GenerateContentConfig(temperature=0.4),
        )
        ai_reco = resp.text.strip()
    except Exception:
        pass

    # ── Step 3: Build complete HTML and yield as one chunk ────────────────────
    html = build_analysis_html(
        analytics=analytics,
        title=title,
        ai_narratives=ai_narratives if ai_narratives else None,
        ai_recommendations=ai_reco,
    )
    yield html


async def chat_stream(
    report_html: str,
    message: str,
    history: list[dict],
    api_key: str | None = None,
) -> AsyncGenerator[str, None]:
    """Stream chat response about the analysis report."""
    client = _make_client(api_key)
    report_text = re.sub(r"<[^>]+>", " ", report_html)
    report_text = re.sub(r"\s+", " ", report_text).strip()[:5000]

    contents: list[dict] = []
    for msg in history[-12:]:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg["content"]}]})
    contents.append({"role": "user", "parts": [{"text": message}]})

    async for chunk in await client.aio.models.generate_content_stream(
        model="gemini-2.5-flash",
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=CHAT_SYSTEM.format(report_summary=report_text),
            temperature=0.5,
        ),
    ):
        if chunk.text:
            yield chunk.text
