"""
Gemini-powered intent parser — agent-style multi-turn conversation.

Returns a natural-language reasoning message PLUS a structured search plan
so the UI can show both the agent's thinking and an editable plan card.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Literal, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

load_dotenv()

# ── Schema ────────────────────────────────────────────────────────────────────

class DateRange(BaseModel):
    start: str = Field(description="ISO start date e.g. '2026-06-10'")
    end:   str = Field(description="ISO end date   e.g. '2026-06-17'")


class TaskGroup(BaseModel):
    """One cabin × one set of routes × dates. Used for structured table imports."""
    origins: list[str] = Field(default_factory=list,
        description="Departure IATA codes for this group")
    destinations: list[str] = Field(default_factory=list,
        description="Destination IATA codes in this cabin group")
    trip_type: Literal["one_way", "round_trip"] = Field("one_way",
        description="'round_trip' when this group is a round-trip batch search")
    # One-way: use date_ranges OR specific_dates
    date_ranges: list[DateRange] = Field(default_factory=list,
        description="ONE-WAY only: date ranges/periods for this group. Empty for round_trip.")
    specific_dates: list[str] = Field(default_factory=list,
        description="ONE-WAY: specific dates. ROUND-TRIP: departure dates (parallel to return_dates).")
    return_dates: list[str] = Field(default_factory=list,
        description="ROUND-TRIP only: return ISO dates, parallel to specific_dates. "
                    "return_dates[i] is the return date for specific_dates[i].")
    cabin: Literal["Y", "W", "C", "F"] = Field("Y",
        description="Single cabin code for this group")
    label: str = Field("", description="Display label e.g. '经济舱（28条航线）'")


class SearchIntent(BaseModel):
    # --- Natural language parts (shown in chat bubble) ---
    reply: str = Field("",
        description="Conversational Chinese reply: briefly restate what was understood, "
                    "list key assumptions made (date selection, default cabins, etc.), "
                    "then end with a summary line. 3-6 sentences. NO markdown headers.")

    # --- Clarification (when info is missing) ---
    clarifying_question: Optional[str] = Field(None,
        description="ONE specific Chinese question if origins/destinations/time are still unclear. "
                    "Null when ready_to_search=true.")

    # --- Structured plan ---
    origins: list[str] = Field(default_factory=list,
        description="Departure city IATA codes e.g. ['LON']")
    destinations: list[str] = Field(default_factory=list,
        description="Arrival city IATA codes e.g. ['BJS','SHA','CTU']")

    # Specific dates (monthly/weekly representative single dates)
    specific_dates: list[str] = Field(default_factory=list,
        description="Representative single ISO dates. Use when user wants monthly/weekly reference points. "
                    "Do NOT use together with date_ranges. Max 16 dates.")

    # Date ranges (when user specifies periods, e.g. '06/10–06/17')
    date_ranges: list[DateRange] = Field(default_factory=list,
        description="Use when user specifies date PERIODS/RANGES, e.g. '06/10 to 06/17'. "
                    "Each entry is {start, end}. Do NOT use together with specific_dates.")

    # Date range (only for single-route daily drill-down with/without weekday filter)
    date_start: Optional[str] = Field(None,
        description="Start date for single-route range search. Use with weekday_filter for weekly patterns.")
    date_end: Optional[str] = Field(None,
        description="End date for single-route range search.")

    # Weekday filter
    weekday_filter: list[int] = Field(default_factory=list,
        description="Days of week to include: 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun. "
                    "Empty = all days. Used for 'every Friday' or 'weekends only' patterns.")

    task_type: Literal["batch", "single"] = Field("batch",
        description="'batch' for multi-route/multi-date comparison matrix; "
                    "'single' for one route with a date range (incl. weekday filter)")

    trip_type: Literal["one_way", "round_trip"] = Field("one_way",
        description="'round_trip' only when user explicitly mentions return flight")

    # Return leg dates (only for round_trip)
    return_dates: list[str] = Field(default_factory=list,
        description="For round_trip: ISO dates of the return leg, e.g. ['2026-07-10']. "
                    "Use when user gives a specific return date or multiple return dates. "
                    "Pairs with specific_dates: outbound[i] + return_dates[i] = one round trip. "
                    "If only one return date given, repeat it for each outbound date.")
    return_date_start: Optional[str] = Field(None,
        description="For round_trip single-mode drill-down: start of return date range.")
    return_date_end: Optional[str] = Field(None,
        description="For round_trip single-mode drill-down: end of return date range.")

    cabins: list[Literal["Y", "W", "C", "F"]] = Field(default_factory=lambda: ["Y", "C"])
    currency: Literal["EUR", "GBP", "USD", "CNY", "HKD"] = "GBP"
    ready_to_search: bool = Field(False,
        description="True when origins + destinations + (specific_dates OR date_ranges OR date_start) are all set")

    # Structured table import — per-cabin task groups
    task_groups: list[TaskGroup] = Field(default_factory=list,
        description="ONLY for structured table input (rows with 航线, 日期段, 类型, 舱位 columns). "
                    "Each group = one cabin × its destinations × date ranges. "
                    "When non-empty: origins/destinations/specific_dates/date_ranges stay empty, "
                    "ready_to_search=true is implied.")


# ── System prompt ─────────────────────────────────────────────────────────────

_TODAY = datetime.now().strftime("%Y-%m-%d")

SYSTEM_PROMPT = f"""你是一个专业的航班比价 AI 助手，帮助航司商务团队规划多航线批量价格对比任务。今天是 {_TODAY}。

## 你的工作方式
像一个有经验的同事：先复述你理解的需求，说明你做了哪些推断，然后给出完整计划。
用第一人称、自然流畅的中文回复，不要用 markdown 标题，3-6句话。

## 回复结构（reply 字段）
1. 复述理解（"你想对比…"）
2. 说明推断（"我帮你选了…作为代表日期"、"默认同时搜经济舱和商务舱"）
3. 总结（"一共X条航线×Y个日期×Z个舱位，共N次查询"）

如果信息不完整，只问一个最关键的问题，其余尽量用合理默认值。

## IATA代码规则（最高优先级）
**任何3字母大写代码（如 NNG、AKL、BKK、SGN 等）直接视为有效的IATA机场/城市代码，原样使用，绝对不要要求用户澄清是哪个城市。**
用户作为航司商务人员，输入的3字母代码100%准确，你只需直接使用它们。

## 城市 IATA 参考（不全，用户输入任意3字母代码时直接用）
**中国内地**
北京=BJS, 上海=SHA, 广州=CAN, 深圳=SZX, 成都=CTU, 重庆=CKG
杭州=HGH, 南京=NKG, 武汉=WUH, 西安=XIY, 昆明=KMG, 厦门=XMN, 青岛=TAO
大连=DLC, 沈阳=SHE, 哈尔滨=HRB, 长沙=CSX, 郑州=CGO, 福州=FOC
南宁=NNG, 温州=WNZ, 贵阳=KWE, 南昌=KHN, 合肥=HFE, 济南=TNA

**中国港澳台**
香港=HKG, 澳门=MFM, 台北=TPE

**东南亚**
新加坡=SIN, 曼谷=BKK, 胡志明市=SGN, 河内=HAN, 吉隆坡=KUL
马尼拉=MNL, 雅加达=CGK, 巴厘岛=DPS, 金边=PNH, 仰光=RGN

**东北亚**
东京=TYO, 大阪=KIX, 首尔=ICN, 名古屋=NGO, 福冈=FUK

**大洋洲**
悉尼=SYD, 墨尔本=MEL, 奥克兰=AKL, 布里斯班=BNE

**欧洲**
伦敦=LON, 巴黎=PAR, 法兰克福=FRA, 阿姆斯特丹=AMS, 莫斯科=MOW
罗马=ROM, 马德里=MAD, 苏黎世=ZRH, 维也纳=VIE, 曼彻斯特=MAN

**中东 & 南亚**
迪拜=DXB, 阿布扎比=AUH, 多哈=DOH, 孟买=BOM, 新德里=DEL

**美洲**
纽约=NYC, 洛杉矶=LAX, 旧金山=SFO, 温哥华=YVR, 多伦多=YYZ

城市组合：
"主要内地城市" → ["BJS","SHA","CAN","CTU","SZX","HGH"]
"北方城市" → ["BJS","DLC","SHE","HRB"]
"华南城市" → ["CAN","SZX","XMN","HKG"]
"更多内地城市" → ["CGO","CSX","FOC","WUH","XIY","KMG"]
"全部内地/所有中国城市" → ["BJS","SHA","CAN","CTU","SZX","HGH","CGO","CSX","FOC","WUH","XIY","KMG"]

## 任务类型决策（关键！先看路线数量再看日期）

**规则1（最高优先级）**：destinations 有 2 个或以上城市 → task_type 必须是 "batch"，无例外。
**规则2**：用户提供了多个时间段（date_ranges 有 2 个或以上）→ task_type="batch"。
**规则3**：只有满足以下全部条件才能用 task_type="single"：
  - destinations 只有 1 个城市
  - 用户要求连续日期范围（"每天"、"6月1日到30日"）
  - date_ranges 为空

示例：
- "LON→BJS/CTU，4个时间段" → destinations=["BJS","CTU"]，task_type="batch"，date_ranges=[...]
- "LON→BJS，6月每天" → destinations=["BJS"]，task_type="single"，date_start/date_end
- "LON→BJS，06/10-06/17和07/15-07/22" → destinations=["BJS"]，task_type="batch"，date_ranges=[...]

## 日期策略（关键！）

### 何时用 specific_dates（单个代表日）：
用户说的是"某时间段的代表日"或没有指定具体范围时：
- "今夏" → specific_dates=["2026-06-10","2026-07-15","2026-08-12","2026-09-09"]
- "Q3" → specific_dates=["2026-07-15","2026-08-12","2026-09-09"]
- "6月" → specific_dates=["2026-06-10"]
- "下半年" → specific_dates=["2026-07-15","2026-08-12","2026-09-09","2026-10-14","2026-11-11","2026-12-09"]
- 每周代表日："6月按周" → specific_dates=["2026-06-03","2026-06-10","2026-06-17","2026-06-24"]
- 最多16个

### 何时用 date_ranges（时间段）：
用户明确提供了「开始日-结束日」形式的时间段，比如：
- "06/10到06/17、07/15到07/22" → date_ranges=[{{"start":"2026-06-10","end":"2026-06-17"}},{{"start":"2026-07-15","end":"2026-07-22"}}]
- 单程表格中 "2026-06-10 | 2026-06-17" → date_ranges（日期区间从06-10到06-17）
- 往返表格中 "2026-06-10 | 2026-06-17" → specific_dates+return_dates 日期对（见结构化表格识别规则）
- 注意：specific_dates 和 date_ranges 只用其中一个，不要同时填

### 单线详查（task_type="single"，用 date_start/date_end + 可选 weekday_filter）：
- "6月每天LON→BJS" → date_start="2026-06-01", date_end="2026-06-30"
- "6月每周五LON→BJS" → date_start="2026-06-01", date_end="2026-06-30", weekday_filter=[4]
- "夏季每周一LON→BJS" → date_start="2026-06-01", date_end="2026-08-31", weekday_filter=[0]

### 单线详查（task_type="single"，用 date_start/date_end + 可选 weekday_filter）：
- "6月每天LON→BJS" → date_start="2026-06-01", date_end="2026-06-30"
- "6月每周五LON→BJS" → date_start="2026-06-01", date_end="2026-06-30", weekday_filter=[4]
- "夏季每周一LON→BJS" → date_start="2026-06-01", date_end="2026-08-31", weekday_filter=[0]
- 用户给了具体日期就用具体日期

## 往返（round_trip）核心概念

**往返是一个 package，不是两段单程。** 每次查询返回的是出发+返回组合的总价，1对日期 = 1次查询。

当 trip_type="round_trip" 时，出发日和返程日必须分开存放：
- **出发日** → specific_dates / date_start / date_end（与单程逻辑相同）
- **返程日** → return_dates / return_date_start / return_date_end（专用字段）

**绝对禁止**：将返程日放进 date_end，例如"6月10日出发、7月10日返回"绝不能写成 date_start=2026-06-10, date_end=2026-07-10——这会被理解为31天每天搜索。

典型场景：
- 单次往返（"6/10出发，7/10返回"，1条航线）→ task_type="single", date_start="2026-06-10", date_end="2026-06-10", return_date_start="2026-07-10"
- 多次往返批量（"LON→BJS/CTU，4对日期"）→ task_type="batch", 用 task_groups，每组 trip_type="round_trip", specific_dates=[去程日], return_dates=[对应返程日]
- 往返区间（"6月每天出发，7月某天返回"）→ task_type="single", date_start/date_end=出发区间, return_date_start/return_date_end=返程区间

task_type="single" 条件（往返场景）：destinations只有1个城市 AND 用户只给了一个出发日+一个返程日。

回复中说明：X条航线，Y对往返日期，共Z次查询（往返是 package，每对日期只查1次）。

## 币种默认
**默认币种永远是 GBP（英镑），除非用户明确指定其他币种。**
不要根据出发地或目的地推断币种。即使航线是中国城市，也用 GBP，不要改成 CNY/HKD。

## 舱位默认
默认 ["Y","C"]（同时查经济舱和商务舱），除非用户明确指定

## 舱位代码映射（YCWF 四档）
- Y = 经济舱
- W = 超级经济舱（又称：豪华经济舱 / 高端经济舱 / Premium Economy / Plus经济舱 / 特级经济舱）
  识别关键词：超级经济 / 豪华经济 / premium economy / PE舱 / 优选经济 / 特选经济
  → 凡含以上词汇，一律映射到 W，不要映射到 Y 或 C
- C = 商务舱 / 公务舱 / Business Class
- F = 头等舱 / First Class

结构化表格舱位映射补充：超级经济舱/豪华经济舱 → W

## 结构化表格识别（识别优先级：最高，覆盖所有其他规则）

当用户粘贴包含如下格式的多行表格时，**立即进入表格解析模式**，不要询问任何澄清问题。

支持两种格式：

**A. 单程格式**（日期是区间，或只有一个日期）：
```
LON-BJS    2026-06-10 | 2026-06-17    DIRECT    经济舱
LON-CTU    2026-07-15 | 2026-07-22    I+D       公务舱
```
`date1 | date2` = 日期区间（从date1到date2）→ date_ranges, trip_type="one_way"

**B. 往返格式**（用户明确说往返，或表格含"往返"字样，或上下文是往返查询）：
```
LON-BJS    2026-06-10 | 2026-06-17
LON-BJS    2026-07-15 | 2026-07-22
LON-CTU    2026-06-10 | 2026-06-17
```
`date1 | date2` = 去程日期 | 返程日期 → specific_dates + return_dates, trip_type="round_trip"

**判断是否往返**：用户在对话中提到"往返"/"round trip"/"回程"，或表格行中日期间隔明显是旅行周期（7-14天）且上下文说明是往返。

解析规则：
1. **航线格式**：`LON-BJS` → origin=LON, destination=BJS（用-分隔）
2. **类型列**：DIRECT/I+D/I+I 仅作参考标签，忽略即可
3. **舱位映射**：经济舱→Y，超级/豪华/Premium Economy→W，公务舱/商务舱→C，头等舱→F；无舱位列时默认同时生成 Y 和 C 两组
4. **按舱位分组**：同一舱位的所有行合并为一个 TaskGroup
5. 每个 TaskGroup 的 `origins` = 该舱位下所有出发地（去重）
6. 每个 TaskGroup 的 `destinations` = 该舱位下所有目的地（去重，按出现顺序）
7. **单程**：`date_ranges` = 所有唯一日期区间（去重），`trip_type="one_way"`
8. **往返**：`specific_dates` = 所有唯一去程日期（去重，保序），`return_dates` = 对应返程日期（与 specific_dates 并行），`trip_type="round_trip"`
   - 不同航线的相同日期对只保留一份（跨航线共用日期）
9. `label` = 例如 "经济舱（3条航线·4对日期）" 或 "公务舱（3条）"
10. task_groups非空时：顶层 origins/destinations/specific_dates/date_ranges 留空列表
11. `ready_to_search=true`，`task_type="batch"`
12. `reply` 说明：已识别X组任务，往返N条航线×M对日期，合计约K次查询（每对日期1次package查询）
13. **不要问任何问题**，直接返回完整 task_groups

往返示例输出：
```
LON-BJS 2026-06-10|2026-06-17  LON-BJS 2026-07-15|2026-07-22  LON-CTU 2026-06-10|2026-06-17
```
→ task_groups=[
  {{origins:["LON"], destinations:["BJS","CTU"], trip_type:"round_trip",
    specific_dates:["2026-06-10","2026-07-15"], return_dates:["2026-06-17","2026-07-22"],
    date_ranges:[], cabin:"Y", label:"经济舱（2条航线·2对日期）"}},
  {{同上但 cabin:"C", label:"公务舱（2条·2对）"}}
]

## 澄清规则
- ready_to_search=true 条件：(origins非空 AND destinations非空 AND (specific_dates非空 OR date_ranges非空 OR date_start非空)) OR task_groups非空
- 缺少关键信息时：reply 末尾自然地提问，同时把 clarifying_question 填上
- 能推断的就推断，不要问不必要的问题

只返回合法 JSON，严格遵循 schema。"""


# ── Client ────────────────────────────────────────────────────────────────────

def _make_client(api_key: str | None = None) -> genai.Client:
    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise ValueError("GEMINI_API_KEY not set")
    return genai.Client(api_key=key)


# ── Parser ────────────────────────────────────────────────────────────────────

async def parse_intent(
    history: list[dict],
    new_message: str,
    api_key: str | None = None,
) -> SearchIntent:
    client = _make_client(api_key)

    contents: list[dict] = []
    for msg in history:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg["content"]}]})
    contents.append({"role": "user", "parts": [{"text": new_message}]})

    response = await client.aio.models.generate_content(
        model="gemini-2.5-flash",
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=SearchIntent,
        ),
    )

    return SearchIntent.model_validate_json(response.text)


def intent_to_display_message(intent: SearchIntent) -> str:
    """Return the AI's natural reply directly — it already contains reasoning."""
    return intent.reply or "好的，我已整理好搜索计划，请确认后开始。"
