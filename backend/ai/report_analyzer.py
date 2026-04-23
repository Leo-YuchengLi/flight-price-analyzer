"""Gemini-powered report narrative analyzer."""
from __future__ import annotations

import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()


ANALYSIS_PROMPT = """你是一位资深的国际机票价格分析师，请根据以下航班搜索统计数据，
用中文撰写一份简洁专业的价格分析报告（约200-300字）。

报告需要包括：
1. 市场整体价格水平概述
2. 国航（CA）与市场的对比分析（基于国航指数：100=与市场均价持平，>100=偏贵，<100=偏便宜）
3. 直飞 vs 中转的价格差异（如有数据）
4. 最佳出行时间建议（如有多日数据）
5. 一句话核心结论与推荐

输出格式：纯 HTML 片段（不要 DOCTYPE/head/body 标签），
用 <p> 标签分段，关键数字用 <strong> 标签加粗，
不要使用 markdown，不要输出任何说明性文字。"""


def _make_client(api_key: str | None = None) -> genai.Client:
    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise ValueError("GEMINI_API_KEY not set")
    return genai.Client(api_key=key)


async def analyze_report(
    stats: dict,
    title: str,
    user_query: str | None = None,
    api_key: str | None = None,
) -> str:
    """Return an HTML snippet with narrative analysis of the report stats."""
    client = _make_client(api_key)

    data_lines = [
        f"报告标题：{title}",
        f"航线：{stats.get('date_range', '')}，舱位：{stats.get('cabin', 'Y')}，币种：{stats.get('currency', 'EUR')}",
        f"总航班数：{stats.get('total_flights')}，航司数：{stats.get('total_airlines')}",
        f"市场最低价：{stats.get('price_min', 0):.0f}，最高价：{stats.get('price_max', 0):.0f}，均价：{stats.get('price_avg', 0):.0f}",
        f"直飞比例：{stats.get('direct_pct', 0)}%",
    ]
    if stats.get("ca_price_avg"):
        data_lines.append(
            f"国航均价：{stats['ca_price_avg']:.0f}，国航指数（CA Index）：{stats.get('ca_index_avg', 100):.1f}"
        )
    if user_query:
        data_lines.append(f"用户原始查询：「{user_query}」")

    prompt = ANALYSIS_PROMPT + "\n\n统计数据：\n" + "\n".join(data_lines)

    response = await client.aio.models.generate_content(
        model="gemini-2.5-flash",
        contents=[{"role": "user", "parts": [{"text": prompt}]}],
        config=types.GenerateContentConfig(
            temperature=0.4,
        ),
    )

    return response.text.strip()
