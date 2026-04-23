"""City and airport IATA code database with Chinese/English name lookup."""
from __future__ import annotations

# ── Master database ───────────────────────────────────────────────────────────
# Format: city_iata -> {name_en, name_zh, country, region, airports: [airport_iata, ...]}
CITY_DB: dict[str, dict] = {
    # ── UK ────────────────────────────────────────────────────────────────────
    "LON": {"name_en": "London",       "name_zh": "伦敦",   "country": "UK",     "region": "Europe",  "airports": ["LHR","LGW","STN","LTN","LCY"]},
    "MAN": {"name_en": "Manchester",   "name_zh": "曼彻斯特","country": "UK",    "region": "Europe",  "airports": ["MAN"]},
    "BHX": {"name_en": "Birmingham",   "name_zh": "伯明翰", "country": "UK",     "region": "Europe",  "airports": ["BHX"]},
    "EDI": {"name_en": "Edinburgh",    "name_zh": "爱丁堡", "country": "UK",     "region": "Europe",  "airports": ["EDI"]},

    # ── Europe ────────────────────────────────────────────────────────────────
    "PAR": {"name_en": "Paris",        "name_zh": "巴黎",   "country": "France", "region": "Europe",  "airports": ["CDG","ORY"]},
    "AMS": {"name_en": "Amsterdam",    "name_zh": "阿姆斯特丹","country": "Netherlands","region": "Europe","airports": ["AMS"]},
    "FRA": {"name_en": "Frankfurt",    "name_zh": "法兰克福","country": "Germany","region": "Europe",  "airports": ["FRA"]},
    "MUC": {"name_en": "Munich",       "name_zh": "慕尼黑", "country": "Germany","region": "Europe",  "airports": ["MUC"]},
    "MAD": {"name_en": "Madrid",       "name_zh": "马德里", "country": "Spain",  "region": "Europe",  "airports": ["MAD"]},
    "BCN": {"name_en": "Barcelona",    "name_zh": "巴塞罗那","country": "Spain", "region": "Europe",  "airports": ["BCN"]},
    "ROM": {"name_en": "Rome",         "name_zh": "罗马",   "country": "Italy",  "region": "Europe",  "airports": ["FCO","CIA"]},
    "MIL": {"name_en": "Milan",        "name_zh": "米兰",   "country": "Italy",  "region": "Europe",  "airports": ["MXP","LIN"]},
    "ZRH": {"name_en": "Zurich",       "name_zh": "苏黎世", "country": "Switzerland","region": "Europe","airports": ["ZRH"]},
    "VIE": {"name_en": "Vienna",       "name_zh": "维也纳", "country": "Austria","region": "Europe",  "airports": ["VIE"]},
    "CPH": {"name_en": "Copenhagen",   "name_zh": "哥本哈根","country": "Denmark","region": "Europe", "airports": ["CPH"]},
    "HEL": {"name_en": "Helsinki",     "name_zh": "赫尔辛基","country": "Finland","region": "Europe", "airports": ["HEL"]},
    "OSL": {"name_en": "Oslo",         "name_zh": "奥斯陆", "country": "Norway", "region": "Europe",  "airports": ["OSL"]},
    "ARN": {"name_en": "Stockholm",    "name_zh": "斯德哥尔摩","country": "Sweden","region": "Europe","airports": ["ARN"]},
    "BRU": {"name_en": "Brussels",     "name_zh": "布鲁塞尔","country": "Belgium","region": "Europe", "airports": ["BRU"]},
    "LIS": {"name_en": "Lisbon",       "name_zh": "里斯本", "country": "Portugal","region": "Europe", "airports": ["LIS"]},
    "ATH": {"name_en": "Athens",       "name_zh": "雅典",   "country": "Greece", "region": "Europe",  "airports": ["ATH"]},
    "WAW": {"name_en": "Warsaw",       "name_zh": "华沙",   "country": "Poland", "region": "Europe",  "airports": ["WAW"]},
    "PRG": {"name_en": "Prague",       "name_zh": "布拉格", "country": "Czech",  "region": "Europe",  "airports": ["PRG"]},
    "BUD": {"name_en": "Budapest",     "name_zh": "布达佩斯","country": "Hungary","region": "Europe",  "airports": ["BUD"]},
    "GVA": {"name_en": "Geneva",       "name_zh": "日内瓦", "country": "Switzerland","region": "Europe","airports": ["GVA"]},

    # ── China Mainland ────────────────────────────────────────────────────────
    "BJS": {"name_en": "Beijing",      "name_zh": "北京",   "country": "China",  "region": "Asia",    "airports": ["PEK","PKX"]},
    "SHA": {"name_en": "Shanghai",     "name_zh": "上海",   "country": "China",  "region": "Asia",    "airports": ["PVG","SHA"]},
    "CAN": {"name_en": "Guangzhou",    "name_zh": "广州",   "country": "China",  "region": "Asia",    "airports": ["CAN"]},
    "SZX": {"name_en": "Shenzhen",     "name_zh": "深圳",   "country": "China",  "region": "Asia",    "airports": ["SZX"]},
    "CTU": {"name_en": "Chengdu",      "name_zh": "成都",   "country": "China",  "region": "Asia",    "airports": ["CTU","TFU"]},
    "CKG": {"name_en": "Chongqing",    "name_zh": "重庆",   "country": "China",  "region": "Asia",    "airports": ["CKG"]},
    "XIY": {"name_en": "Xi'an",        "name_zh": "西安",   "country": "China",  "region": "Asia",    "airports": ["XIY"]},
    "WUH": {"name_en": "Wuhan",        "name_zh": "武汉",   "country": "China",  "region": "Asia",    "airports": ["WUH"]},
    "HGH": {"name_en": "Hangzhou",     "name_zh": "杭州",   "country": "China",  "region": "Asia",    "airports": ["HGH"]},
    "NKG": {"name_en": "Nanjing",      "name_zh": "南京",   "country": "China",  "region": "Asia",    "airports": ["NKG"]},
    "KMG": {"name_en": "Kunming",      "name_zh": "昆明",   "country": "China",  "region": "Asia",    "airports": ["KMG"]},
    "TAO": {"name_en": "Qingdao",      "name_zh": "青岛",   "country": "China",  "region": "Asia",    "airports": ["TAO"]},
    "XMN": {"name_en": "Xiamen",       "name_zh": "厦门",   "country": "China",  "region": "Asia",    "airports": ["XMN"]},
    "HAK": {"name_en": "Haikou",       "name_zh": "海口",   "country": "China",  "region": "Asia",    "airports": ["HAK"]},
    "TNA": {"name_en": "Jinan",        "name_zh": "济南",   "country": "China",  "region": "Asia",    "airports": ["TNA"]},
    "SHE": {"name_en": "Shenyang",     "name_zh": "沈阳",   "country": "China",  "region": "Asia",    "airports": ["SHE"]},
    "HRB": {"name_en": "Harbin",       "name_zh": "哈尔滨", "country": "China",  "region": "Asia",    "airports": ["HRB"]},
    "CGO": {"name_en": "Zhengzhou",    "name_zh": "郑州",   "country": "China",  "region": "Asia",    "airports": ["CGO"]},
    "TSN": {"name_en": "Tianjin",      "name_zh": "天津",   "country": "China",  "region": "Asia",    "airports": ["TSN"]},
    "NNG": {"name_en": "Nanning",      "name_zh": "南宁",   "country": "China",  "region": "Asia",    "airports": ["NNG"]},
    "URC": {"name_en": "Urumqi",       "name_zh": "乌鲁木齐","country": "China", "region": "Asia",    "airports": ["URC"]},

    # ── HK / TW / MO ─────────────────────────────────────────────────────────
    "HKG": {"name_en": "Hong Kong",    "name_zh": "香港",   "country": "HK",     "region": "Asia",    "airports": ["HKG"]},
    "TPE": {"name_en": "Taipei",       "name_zh": "台北",   "country": "TW",     "region": "Asia",    "airports": ["TPE","TSA"]},
    "MFM": {"name_en": "Macau",        "name_zh": "澳门",   "country": "MO",     "region": "Asia",    "airports": ["MFM"]},

    # ── Asia Pacific ──────────────────────────────────────────────────────────
    "TYO": {"name_en": "Tokyo",        "name_zh": "东京",   "country": "Japan",  "region": "Asia",    "airports": ["NRT","HND"]},
    "OSA": {"name_en": "Osaka",        "name_zh": "大阪",   "country": "Japan",  "region": "Asia",    "airports": ["KIX","ITM"]},
    "ICN": {"name_en": "Seoul",        "name_zh": "首尔",   "country": "Korea",  "region": "Asia",    "airports": ["ICN","GMP"]},
    "BKK": {"name_en": "Bangkok",      "name_zh": "曼谷",   "country": "Thailand","region": "Asia",   "airports": ["BKK","DMK"]},
    "SIN": {"name_en": "Singapore",    "name_zh": "新加坡", "country": "Singapore","region": "Asia",  "airports": ["SIN"]},
    "KUL": {"name_en": "Kuala Lumpur", "name_zh": "吉隆坡","country": "Malaysia","region": "Asia",   "airports": ["KUL"]},
    "DXB": {"name_en": "Dubai",        "name_zh": "迪拜",   "country": "UAE",    "region": "Middle East","airports": ["DXB"]},
    "IST": {"name_en": "Istanbul",     "name_zh": "伊斯坦布尔","country": "Turkey","region": "Middle East","airports": ["IST"]},
    "DOH": {"name_en": "Doha",         "name_zh": "多哈",   "country": "Qatar",  "region": "Middle East","airports": ["DOH"]},
    "BOM": {"name_en": "Mumbai",       "name_zh": "孟买",   "country": "India",  "region": "Asia",    "airports": ["BOM"]},
    "DEL": {"name_en": "Delhi",        "name_zh": "德里",   "country": "India",  "region": "Asia",    "airports": ["DEL"]},
    "SYD": {"name_en": "Sydney",       "name_zh": "悉尼",   "country": "Australia","region": "Oceania","airports": ["SYD"]},
    "MEL": {"name_en": "Melbourne",    "name_zh": "墨尔本", "country": "Australia","region": "Oceania","airports": ["MEL"]},

    # ── Americas ──────────────────────────────────────────────────────────────
    "NYC": {"name_en": "New York",     "name_zh": "纽约",   "country": "USA",    "region": "Americas","airports": ["JFK","EWR","LGA"]},
    "LAX": {"name_en": "Los Angeles",  "name_zh": "洛杉矶","country": "USA",    "region": "Americas","airports": ["LAX"]},
    "SFO": {"name_en": "San Francisco","name_zh": "旧金山","country": "USA",    "region": "Americas","airports": ["SFO"]},
    "ORD": {"name_en": "Chicago",      "name_zh": "芝加哥", "country": "USA",    "region": "Americas","airports": ["ORD","MDW"]},
    "SEA": {"name_en": "Seattle",      "name_zh": "西雅图", "country": "USA",    "region": "Americas","airports": ["SEA"]},
    "BOS": {"name_en": "Boston",       "name_zh": "波士顿", "country": "USA",    "region": "Americas","airports": ["BOS"]},
    "YVR": {"name_en": "Vancouver",    "name_zh": "温哥华", "country": "Canada", "region": "Americas","airports": ["YVR"]},
    "YYZ": {"name_en": "Toronto",      "name_zh": "多伦多", "country": "Canada", "region": "Americas","airports": ["YYZ"]},
}

# ── Airport → City reverse map ────────────────────────────────────────────────
AIRPORT_TO_CITY: dict[str, str] = {}
for _city_iata, _info in CITY_DB.items():
    for _ap in _info["airports"]:
        AIRPORT_TO_CITY[_ap] = _city_iata

# ── Name → IATA reverse map ───────────────────────────────────────────────────
_NAME_TO_IATA: dict[str, str] = {}
for _city_iata, _info in CITY_DB.items():
    _NAME_TO_IATA[_info["name_en"].lower()] = _city_iata
    _NAME_TO_IATA[_info["name_zh"]] = _city_iata
    _NAME_TO_IATA[_city_iata.lower()] = _city_iata
    for _ap in _info["airports"]:
        _NAME_TO_IATA[_ap.lower()] = _city_iata


def resolve_iata(query: str) -> str | None:
    """
    Resolve any city name / airport code / Chinese name to a city IATA code.
    Returns None if not found.

    Examples:
        resolve_iata("London")  → "LON"
        resolve_iata("lhr")     → "LON"
        resolve_iata("北京")    → "BJS"
        resolve_iata("PEK")     → "BJS"
        resolve_iata("BJS")     → "BJS"
    """
    q = query.strip()
    # Try exact IATA city code first (case-insensitive)
    upper = q.upper()
    if upper in CITY_DB:
        return upper
    # Try 3-letter airport code
    if upper in AIRPORT_TO_CITY:
        return AIRPORT_TO_CITY[upper]
    # Try name lookup
    lower = q.lower()
    return _NAME_TO_IATA.get(lower) or _NAME_TO_IATA.get(q)


def city_name(iata: str, lang: str = "zh") -> str:
    """Return human-readable city name for display."""
    info = CITY_DB.get(iata.upper())
    if not info:
        return iata
    return info["name_zh"] if lang == "zh" else info["name_en"]


def all_cities() -> list[dict]:
    """Return all cities as list of dicts for autocomplete."""
    return [
        {
            "iata": iata,
            "name_en": info["name_en"],
            "name_zh": info["name_zh"],
            "country": info["country"],
            "region": info["region"],
        }
        for iata, info in CITY_DB.items()
    ]
