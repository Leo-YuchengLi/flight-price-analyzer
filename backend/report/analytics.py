"""
Report analytics — enrich and pivot flight data.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date as dt_date, datetime as dt_datetime, timedelta
from typing import Any

CA_CODE = "CA"

# Key airlines shown as dedicated columns in both sheets
KEY_AIRLINE_CODES = {"CA", "CZ", "MU", "BA", "VS", "HU"}

CABIN_LABEL   = {"Y": "经济舱", "C": "商务舱", "F": "头等舱"}

# Internal category → Excel TYPE label
# D  : direct (0 stops)
# ID : International → Domestic (destination is mainland China)
# II : International → International (destination outside mainland China)
CATEGORY_DISPLAY = {"D": "DIRECT", "ID": "ID", "II": "II"}

# Mainland China city/airport codes (used for transit & destination classification)
CHINESE_CITIES: frozenset[str] = frozenset([
    "BJS", "PEK", "PKX", "NAY",
    "SHA", "PVG",
    "CAN", "SZX", "ZUH",
    "CTU", "TFU", "KMG",
    "CGO", "WUH", "CSX",
    "XIY", "LHW", "INC", "URC",
    "HGH", "NKG", "NGB", "WNZ", "CZX", "HFE",
    "DLC", "SHE", "HRB", "CGQ",
    "TSN", "TYN", "SJW", "HET",
    "XMN", "FOC", "TAO", "TNA",
    "HAK", "SYX", "NNG", "KWE",
    "KHN", "LYI", "YTY", "NTG",
])

MAX_STOPS    = 1   # exclude 2+ connection itineraries
MAX_LAYOVER_H = 24  # exclude connections with layover > 24 hours between segments


# ── Layover filter ────────────────────────────────────────────────────────────

def _has_excessive_layover(flight: dict, max_hours: int = MAX_LAYOVER_H) -> bool:
    """Return True if any layover in the itinerary exceeds max_hours."""
    segs = flight.get("segments", [])
    for i in range(len(segs) - 1):
        try:
            arr = dt_datetime.fromisoformat(
                f"{segs[i]['arrival_date']}T{segs[i]['arrival_time']}:00")
            dep = dt_datetime.fromisoformat(
                f"{segs[i+1]['departure_date']}T{segs[i+1]['departure_time']}:00")
            if (dep - arr) > timedelta(hours=max_hours):
                return True
        except Exception:
            pass
    return False


# ── Stop-type classification ──────────────────────────────────────────────────

def classify_stop_type(flight: dict) -> str:
    """
    DIRECT : 0 stops
    ID     : International origin → Domestic destination (mainland China)
    II     : International origin → International destination
    Classification is based solely on origin/destination, not transit cities.
    """
    if flight.get("is_direct") or int(flight.get("stops", 0)) == 0:
        return "D"

    dest = flight.get("destination", "").upper()
    return "ID" if dest in CHINESE_CITIES else "II"


# ── Date period label ─────────────────────────────────────────────────────────

def format_date_period(date_str: str, all_dates: list[str] | None = None) -> tuple[str, str]:
    """
    Column header label for a searched date.

    Always shows the actual searched date (e.g. '10 JUN') in the sub-label,
    regardless of how the dates are spaced. This avoids confusing calendar-week
    ranges (8JUN-14JUN) that imply an entire week was searched when only one
    date was queried.

    For consecutive daily sequences (avg gap ≤ 1 day) the date is shown as-is.
    All other cases (weekly reps, monthly reps, single date) show 'D MON'.
    """
    d = dt_date.fromisoformat(date_str)
    month_yr = f"{d.strftime('%b').upper()} {d.year}"
    day_label = f"{d.day} {d.strftime('%b').upper()}"
    return month_yr, day_label


# ── Enrich flights ────────────────────────────────────────────────────────────

# Approximate cross rates TO HKD.  Good enough for relative price comparison —
# we are never doing precise financial accounting, just ranking/indexing.
_APPROX_TO_HKD: dict[str, float] = {
    "HKD": 1.0,
    "CNY": 1.09,   # ≈ 1 CNY = 1.09 HKD
    "USD": 7.80,
    "EUR": 8.45,
    "GBP": 9.80,
    "JPY": 0.052,
    "SGD": 5.78,
    "THB": 0.22,
    "AUD": 4.95,
    "CAD": 5.60,
}


def _normalize_currency(flights: list[dict]) -> list[dict]:
    """Convert all flights to the dominant currency using approximate exchange rates.
    No flights are ever dropped — minority-currency prices are converted instead.
    This allows merging reports searched in different currencies (e.g. HKD + CNY).
    """
    if not flights:
        return flights
    from collections import Counter
    counts = Counter(f.get("currency", "") for f in flights)
    dominant = counts.most_common(1)[0][0]

    # Fast path: already uniform
    if counts[dominant] == len(flights):
        return flights

    dom_rate = _APPROX_TO_HKD.get(dominant, 1.0)   # dominant currency → HKD
    result: list[dict] = []
    for f in flights:
        src_cur = f.get("currency", dominant)
        if src_cur == dominant:
            result.append(f)
        else:
            # Convert: src → HKD → dominant
            src_rate = _APPROX_TO_HKD.get(src_cur, 1.0)
            factor = src_rate / dom_rate
            converted = dict(f)
            converted["price"]    = round(f.get("price", 0) * factor, 0)
            converted["currency"] = dominant
            result.append(converted)
    return result


def enrich_flights(flights: list[dict]) -> list[dict]:
    """Classify + add market metrics to every flight."""
    # Normalize to dominant currency
    flights = _normalize_currency(flights)
    # Drop 2+ stop and excessive-layover itineraries
    flights = [f for f in flights
               if int(f.get("stops", 0)) <= MAX_STOPS
               and not _has_excessive_layover(f)]

    for f in flights:
        f["category"]     = classify_stop_type(f)
        f["type_display"] = CATEGORY_DISPLAY.get(f["category"], f["category"])

    groups: dict[tuple, list[dict]] = defaultdict(list)
    for f in flights:
        key = (f["departure_date"], f["origin"], f["destination"],
               f["category"], f["cabin"])
        groups[key].append(f)

    enriched: list[dict] = []
    for group in groups.values():
        valid       = [f for f in group if f["price"] > 0]
        market_min  = min((f["price"] for f in valid), default=0)
        ca_list     = [f for f in valid if f["airline_code"] == CA_CODE]
        ca_price    = ca_list[0]["price"] if ca_list else None

        sorted_prices = sorted(set(f["price"] for f in valid))
        overall_rank  = {p: i + 1 for i, p in enumerate(sorted_prices)}

        key_prices = [f["price"] for f in valid
                      if f["airline_code"] in KEY_AIRLINE_CODES]
        key_sorted  = sorted(set(key_prices))
        key_rank    = {p: i + 1 for i, p in enumerate(key_sorted)}

        for f in group:
            e = f.copy()
            e["market_min"]    = market_min
            e["market_rank"]   = overall_rank.get(f["price"], 0)
            e["ca_price"]      = ca_price
            e["ca_index"]      = (
                round(ca_price / market_min * 100, 1)
                if (ca_price and market_min) else None
            )
            e["ca_key_rank"]   = key_rank.get(ca_price, None) if ca_price else None
            e["ca_all_rank"]   = overall_rank.get(ca_price, None) if ca_price else None
            e["vs_min_index"]  = (
                round(f["price"] / market_min * 100, 1) if market_min else None
            )
            enriched.append(e)

    enriched.sort(key=lambda x: (
        x["origin"], x["destination"], x["departure_date"],
        x.get("type_display", ""), x["price"]
    ))
    return enriched


# ── Build matrix data for Excel ───────────────────────────────────────────────

def build_excel_data(flights: list[dict]) -> dict[str, Any]:
    """
    Build all pivot data needed for the two Excel sheets.

    Returns:
    {
      "dates": [sorted date strings],
      "matrix_rows": [
        {
          "type_label": "DIRECT" | "HD" | "H",
          "route": "LON-BJS",
          "cabin": "Y" | "C",
          "cabin_label": "经济舱" | "商务舱",
          "date_data": {
            "2026-06-10": {
              "CA": price | None,
              "CZ": price | None,
              "MU": price | None,
              "BA_VS": (price, "BA"|"VS") | None,
              "HU": price | None,
              "other_min": (price, airline_name) | None,
            },
            ...
          },
        },
        ...
      ],
      "detail_rows": [flat list for 详细数据 sheet],
    }
    """
    # Normalize to dominant currency + drop excessive-stop/layover flights
    flights = _normalize_currency(flights)
    flights = [f for f in flights
               if int(f.get("stops", 0)) <= MAX_STOPS
               and not _has_excessive_layover(f)]

    for f in flights:
        if "category" not in f:
            f["category"] = classify_stop_type(f)
        if "type_display" not in f:
            f["type_display"] = CATEGORY_DISPLAY.get(f["category"], f["category"])

    dates = sorted(set(f["departure_date"] for f in flights))

    # ── Per-cell minimums: (route, cabin, type_label, date) → {code: min_price}
    cell_prices: dict[tuple, dict[str, float]] = defaultdict(dict)
    for f in flights:
        if f["price"] <= 0:
            continue
        route = f"{f['origin']}-{f['destination']}"
        key   = (route, f["cabin"], f["type_display"], f["departure_date"])
        code  = f["airline_code"]
        if code not in cell_prices[key] or f["price"] < cell_prices[key][code]:
            cell_prices[key][code] = f["price"]

    # ── Collect (type_label, route, cabin) tuples in display order ────────────
    TYPE_ORDER = {"DIRECT": 0, "ID": 1, "II": 2}
    CABIN_ORDER = {"Y": 0, "C": 1, "F": 2}

    row_keys: set[tuple] = set()
    for (route, cabin, type_label, _date) in cell_prices:
        row_keys.add((type_label, route, cabin))

    sorted_row_keys = sorted(
        row_keys,
        key=lambda t: (TYPE_ORDER.get(t[0], 9), t[1], CABIN_ORDER.get(t[2], 9))
    )

    # ── Build matrix_rows ─────────────────────────────────────────────────────
    matrix_rows = []
    for (type_label, route, cabin) in sorted_row_keys:
        date_data = {}
        for date in dates:
            key    = (route, cabin, type_label, date)
            prices = cell_prices.get(key, {})
            if not prices:
                date_data[date] = None
                continue

            ca_p  = prices.get("CA")
            cz_p  = prices.get("CZ")
            mu_p  = prices.get("MU")
            ba_p  = prices.get("BA")
            vs_p  = prices.get("VS")
            hu_p  = prices.get("HU")

            # BA/VS: pick whichever is cheaper
            ba_vs = None
            if ba_p is not None and vs_p is not None:
                ba_vs = (min(ba_p, vs_p), "BA" if ba_p <= vs_p else "VS")
            elif ba_p is not None:
                ba_vs = (ba_p, "BA")
            elif vs_p is not None:
                ba_vs = (vs_p, "VS")

            # "lowest fare(other)" = global market minimum across ALL airlines
            other_min = None
            if prices:
                best_code = min(prices, key=prices.__getitem__)
                airline_name = next(
                    (f["airline"] for f in flights
                     if f["airline_code"] == best_code), best_code
                )
                other_min = (prices[best_code], airline_name)

            date_data[date] = {
                "CA":    ca_p,
                "CZ":    cz_p,
                "MU":    mu_p,
                "BA_VS": ba_vs,
                "HU":    hu_p,
                "other": other_min,
            }

        matrix_rows.append({
            "type_label":  type_label,
            "route":       route,
            "cabin":       cabin,
            "cabin_label": CABIN_LABEL.get(cabin, cabin),
            "date_data":   date_data,
        })

    # Matrix: only keep rows that have CA price in at least one date column
    matrix_rows = [
        r for r in matrix_rows
        if any(
            dd is not None and dd.get("CA") is not None
            for dd in r["date_data"].values()
        )
    ]

    # ── Build detail_rows ─────────────────────────────────────────────────────
    # One row per (route, date, type_label, cabin)
    detail_keys: dict[tuple, dict] = {}
    airline_names: dict[str, str] = {}

    for f in flights:
        airline_names[f["airline_code"]] = f["airline"]
        if f["price"] <= 0:
            continue
        route = f"{f['origin']}-{f['destination']}"
        key   = (route, f["departure_date"], f["type_display"], f["cabin"])

        if key not in detail_keys:
            detail_keys[key] = {
                "route": route, "date": f["departure_date"],
                "type": f["type_display"], "cabin_label": CABIN_LABEL.get(f["cabin"], f["cabin"]),
                "prices": defaultdict(lambda: None),
                "all_prices": [],
            }
        row = detail_keys[key]
        code = f["airline_code"]
        cur  = row["prices"][code]
        if cur is None or f["price"] < cur:
            row["prices"][code] = f["price"]
        row["all_prices"].append(f["price"])

    detail_rows = []
    for key in sorted(detail_keys):
        row    = detail_keys[key]
        prices = row["prices"]
        all_p  = [p for p in row["all_prices"] if p > 0]

        ca_p  = prices["CA"]
        cz_p  = prices["CZ"]
        mu_p  = prices["MU"]
        ba_p  = prices["BA"]
        vs_p  = prices["VS"]
        hu_p  = prices["HU"]

        # BA/VS combined
        ba_vs_p = None
        ba_vs_name = ""
        if ba_p is not None and vs_p is not None:
            if ba_p <= vs_p:
                ba_vs_p, ba_vs_name = ba_p, "BA"
            else:
                ba_vs_p, ba_vs_name = vs_p, "VS"
        elif ba_p is not None:
            ba_vs_p, ba_vs_name = ba_p, "BA"
        elif vs_p is not None:
            ba_vs_p, ba_vs_name = vs_p, "VS"

        # Global market minimum (lowest fare across ALL airlines)
        market_min = min(all_p) if all_p else None
        min_name   = ""
        if market_min is not None:
            for code, p in prices.items():
                if p == market_min:
                    min_name = airline_names.get(code, code)
                    break

        # CA index: CA price / market_min × 100
        ca_index = (
            round(ca_p / market_min * 100, 1)
            if (ca_p and market_min) else None
        )

        # CA rank among ALL airlines (1 = cheapest)
        all_p_sorted = sorted(all_p)
        ca_all_rank = (all_p_sorted.index(ca_p) + 1) if (ca_p and ca_p in all_p_sorted) else None

        # CA rank among key airlines only
        key_p_list = sorted(p for c, p in prices.items()
                            if c in KEY_AIRLINE_CODES and p is not None)
        ca_key_rank = (key_p_list.index(ca_p) + 1) if (ca_p and ca_p in key_p_list) else None

        detail_rows.append({
            "route":       row["route"],
            "date":        row["date"],
            "type":        row["type"],
            "cabin":       row["cabin_label"],
            "CA":          ca_p,
            "CZ":          cz_p,
            "MU":          mu_p,
            "BA_VS":       ba_vs_p,
            "BA_VS_name":  ba_vs_name,
            "HU":          hu_p,
            "market_min":  market_min,   # lowest fare(other) = global minimum
            "min_airline": min_name,     # airline with global minimum
            "ca_index":    ca_index,
            "ca_key_rank": ca_key_rank,
            "ca_all_rank": ca_all_rank,
        })

    return {
        "dates":       dates,
        "matrix_rows": matrix_rows,
        "detail_rows": detail_rows,
    }


# ── Period-aggregated matrix (for date-range searches) ───────────────────────

def build_period_excel_data(flights: list[dict], date_ranges: list[dict]) -> dict[str, Any]:
    """
    Build matrix aggregated by date PERIODS instead of individual days.
    date_ranges: [{"start": "2026-06-10", "end": "2026-06-17"}, ...]
    Each column = one period; cell = min price across all days in that period.
    """
    # Normalize and filter
    flights = _normalize_currency(flights)
    flights = [f for f in flights
               if int(f.get("stops", 0)) <= MAX_STOPS
               and not _has_excessive_layover(f)]

    for f in flights:
        if "category" not in f:
            f["category"] = classify_stop_type(f)
        if "type_display" not in f:
            f["type_display"] = CATEGORY_DISPLAY.get(f["category"], f["category"])

    # Period keys and labels
    period_keys = [f"{r['start']}|{r['end']}" for r in date_ranges]

    def find_period(date_str: str) -> str | None:
        d = dt_date.fromisoformat(date_str)
        for r in date_ranges:
            if dt_date.fromisoformat(r["start"]) <= d <= dt_date.fromisoformat(r["end"]):
                return f"{r['start']}|{r['end']}"
        return None

    def _period_header(pk: str) -> tuple[str, str]:
        start, end = pk.split("|")
        s = dt_date.fromisoformat(start)
        e = dt_date.fromisoformat(end)
        month_yr = f"{s.strftime('%b').upper()} {s.year}"
        if s == e:
            # Single-day period: show exact date
            lbl = f"{s.day} {s.strftime('%b').upper()}"
        elif s.month == e.month:
            # Same month: "8-14 JUN"
            lbl = f"{s.day}-{e.day} {s.strftime('%b').upper()}"
        else:
            # Cross-month: "30MAY-5JUN"
            lbl = f"{s.day}{s.strftime('%b').upper()}-{e.day}{e.strftime('%b').upper()}"
        return month_yr, lbl

    date_labels = {pk: _period_header(pk) for pk in period_keys}

    # cell_prices: (route, cabin, type_label, period_key) → {code: min_price}
    cell_prices: dict[tuple, dict[str, float]] = defaultdict(dict)
    for f in flights:
        if f["price"] <= 0:
            continue
        pk = find_period(f["departure_date"])
        if pk is None:
            continue
        route = f"{f['origin']}-{f['destination']}"
        key   = (route, f["cabin"], f["type_display"], pk)
        code  = f["airline_code"]
        if code not in cell_prices[key] or f["price"] < cell_prices[key][code]:
            cell_prices[key][code] = f["price"]

    TYPE_ORDER  = {"DIRECT": 0, "ID": 1, "DD": 2, "II": 3}
    CABIN_ORDER = {"Y": 0, "C": 1, "F": 2}

    row_keys: set[tuple] = set()
    for (route, cabin, type_label, _pk) in cell_prices:
        row_keys.add((type_label, route, cabin))

    sorted_row_keys = sorted(
        row_keys,
        key=lambda t: (TYPE_ORDER.get(t[0], 9), t[1], CABIN_ORDER.get(t[2], 9))
    )

    matrix_rows = []
    for (type_label, route, cabin) in sorted_row_keys:
        date_data = {}
        for pk in period_keys:
            key    = (route, cabin, type_label, pk)
            prices = cell_prices.get(key, {})
            if not prices:
                date_data[pk] = None
                continue

            ca_p  = prices.get("CA")
            cz_p  = prices.get("CZ")
            mu_p  = prices.get("MU")
            ba_p  = prices.get("BA")
            vs_p  = prices.get("VS")
            hu_p  = prices.get("HU")

            ba_vs = None
            if ba_p is not None and vs_p is not None:
                ba_vs = (min(ba_p, vs_p), "BA" if ba_p <= vs_p else "VS")
            elif ba_p is not None:
                ba_vs = (ba_p, "BA")
            elif vs_p is not None:
                ba_vs = (vs_p, "VS")

            other_min = None
            if prices:
                best_code    = min(prices, key=prices.__getitem__)
                airline_name = next(
                    (f["airline"] for f in flights if f["airline_code"] == best_code),
                    best_code
                )
                other_min = (prices[best_code], airline_name)

            date_data[pk] = {
                "CA": ca_p, "CZ": cz_p, "MU": mu_p,
                "BA_VS": ba_vs, "HU": hu_p, "other": other_min,
            }

        matrix_rows.append({
            "type_label":  type_label,
            "route":       route,
            "cabin":       cabin,
            "cabin_label": CABIN_LABEL.get(cabin, cabin),
            "date_data":   date_data,
        })

    # Matrix: only keep rows that have CA price in at least one period column
    matrix_rows = [
        r for r in matrix_rows
        if any(
            dd is not None and dd.get("CA") is not None
            for dd in r["date_data"].values()
        )
    ]

    # detail_rows — one row per (route, period, type, cabin)
    detail_keys: dict[tuple, dict] = {}
    airline_names: dict[str, str] = {}

    for f in flights:
        airline_names[f["airline_code"]] = f["airline"]
        if f["price"] <= 0:
            continue
        pk = find_period(f["departure_date"])
        if pk is None:
            continue
        route = f"{f['origin']}-{f['destination']}"
        key   = (route, pk, f["type_display"], f["cabin"])

        if key not in detail_keys:
            _, p_lbl = _period_header(pk)
            detail_keys[key] = {
                "route": route, "date": p_lbl,
                "type": f["type_display"],
                "cabin_label": CABIN_LABEL.get(f["cabin"], f["cabin"]),
                "prices": defaultdict(lambda: None),
                "all_prices": [],
            }
        row = detail_keys[key]
        code = f["airline_code"]
        cur  = row["prices"][code]
        if cur is None or f["price"] < cur:
            row["prices"][code] = f["price"]
        row["all_prices"].append(f["price"])

    detail_rows = []
    for key in sorted(detail_keys):
        row    = detail_keys[key]
        prices = row["prices"]
        all_p  = [p for p in row["all_prices"] if p > 0]

        ca_p  = prices["CA"]
        cz_p  = prices["CZ"]
        mu_p  = prices["MU"]
        ba_p  = prices["BA"]
        vs_p  = prices["VS"]
        hu_p  = prices["HU"]

        ba_vs_p, ba_vs_name = None, ""
        if ba_p is not None and vs_p is not None:
            ba_vs_p, ba_vs_name = (ba_p, "BA") if ba_p <= vs_p else (vs_p, "VS")
        elif ba_p is not None:
            ba_vs_p, ba_vs_name = ba_p, "BA"
        elif vs_p is not None:
            ba_vs_p, ba_vs_name = vs_p, "VS"

        market_min  = min(all_p) if all_p else None
        min_name    = ""
        if market_min is not None:
            for code, p in prices.items():
                if p == market_min:
                    min_name = airline_names.get(code, code)
                    break

        ca_index    = (round(ca_p / market_min * 100, 1) if (ca_p and market_min) else None)
        all_p_sorted = sorted(all_p)
        ca_all_rank  = (all_p_sorted.index(ca_p) + 1) if (ca_p and ca_p in all_p_sorted) else None
        key_p_list   = sorted(p for c, p in prices.items()
                               if c in KEY_AIRLINE_CODES and p is not None)
        ca_key_rank  = (key_p_list.index(ca_p) + 1) if (ca_p and ca_p in key_p_list) else None

        detail_rows.append({
            "route": row["route"], "date": row["date"],
            "type": row["type"],  "cabin": row["cabin_label"],
            "CA": ca_p, "CZ": cz_p, "MU": mu_p,
            "BA_VS": ba_vs_p, "BA_VS_name": ba_vs_name, "HU": hu_p,
            "market_min": market_min, "min_airline": min_name,
            "ca_index": ca_index, "ca_key_rank": ca_key_rank, "ca_all_rank": ca_all_rank,
        })

    return {
        "dates":       period_keys,
        "date_labels": date_labels,
        "matrix_rows": matrix_rows,
        "detail_rows": detail_rows,
    }


# ── Legacy helpers (used by HTML report) ─────────────────────────────────────

def build_matrix(flights: list[dict]) -> dict[str, Any]:
    airlines_set: set[str] = set()
    dates_set:    set[str] = set()
    codes: dict[str, str]  = {}

    for f in flights:
        airlines_set.add(f["airline"])
        dates_set.add(f["departure_date"])
        codes[f["airline"]] = f["airline_code"]

    airlines = sorted(airlines_set, key=lambda a: (0 if codes.get(a) == CA_CODE else 1, a))
    dates    = sorted(dates_set)
    cell: dict[tuple, dict] = {}

    for f in flights:
        key = (f["airline"], f["departure_date"])
        if key not in cell or f["price"] < cell[key]["price"]:
            cell[key] = {"price": f["price"], "is_direct": f["is_direct"],
                         "airline_code": f["airline_code"], "is_min": False}

    for date in dates:
        day_prices = [cell[(a, date)]["price"] for a in airlines if (a, date) in cell]
        if day_prices:
            day_min = min(day_prices)
            for a in airlines:
                k = (a, date)
                if k in cell and cell[k]["price"] == day_min:
                    cell[k]["is_min"] = True

    return {"airlines": airlines, "dates": dates, "cell": cell, "codes": codes}


def summary_stats(flights: list[dict]) -> dict[str, Any]:
    if not flights:
        return {}
    prices    = [f["price"] for f in flights if f["price"] > 0]
    ca_prices = [f["price"] for f in flights
                 if f["airline_code"] == CA_CODE and f["price"] > 0]
    airlines  = set(f["airline"] for f in flights)
    routes    = set((f["origin"], f["destination"]) for f in flights)
    direct    = sum(1 for f in flights if f["is_direct"])
    return {
        "total_flights":  len(flights),
        "total_airlines": len(airlines),
        "total_routes":   len(routes),
        "date_range":     (f"{min(f['departure_date'] for f in flights)} ~ "
                           f"{max(f['departure_date'] for f in flights)}"),
        "price_min":      min(prices) if prices else 0,
        "price_max":      max(prices) if prices else 0,
        "price_avg":      round(sum(prices) / len(prices), 0) if prices else 0,
        "direct_pct":     round(direct / len(flights) * 100, 1) if flights else 0,
        "ca_price_avg":   round(sum(ca_prices) / len(ca_prices), 0) if ca_prices else None,
        "currency":       flights[0]["currency"] if flights else "",
        "cabin":          flights[0]["cabin"] if flights else "",
        "generated_at":   __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
