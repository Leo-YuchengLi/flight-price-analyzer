"""
CA-centric price analytics engine.
Computes Air China competitive metrics from enriched flight data.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date as dt_date
from typing import Any

from report.analytics import (
    _has_excessive_layover, _normalize_currency,
    CATEGORY_DISPLAY, MAX_STOPS, classify_stop_type,
)

CABIN_LABEL   = {"Y": "经济舱", "C": "公务舱", "F": "头等舱"}
TYPE_ORDER    = {"DIRECT": 0, "ID": 1, "II": 2}
CABIN_ORDER   = {"Y": 0, "C": 1, "F": 2}
KEY_AIRLINES  = {"CA", "CZ", "MU", "BA", "VS", "HU"}


def compute_ca_analytics(
    flights: list[dict],
    date_ranges: list[dict] | None = None,
    cabin_filter: list[str] | None = None,
    type_filter: list[str] | None = None,
) -> dict[str, Any]:
    """
    Compute Air China competitive analytics.

    Returns:
        {
          "currency": "HKD",
          "cabins": {
            "Y": {
              "label": "经济舱",
              "total_combos": 116,
              "ca_cheapest_count": 10,
              "ca_below_avg_count": 77,
              "ca_above_avg_count": 38,
              "ca_missing_count": 1,
              "ca_avg_index": 122.1,
              "ca_below_avg_pct": 67.0,
              "routes": [
                {
                  "route": "LON-BJS",
                  "type": "DIRECT",
                  "periods": [{
                    "period": "2026-06-10 | 2026-06-17",
                    "ca": 752, "cz": 678, "mu": 694,
                    "ba_vs": 925, "ba_vs_name": "BA", "hu": None,
                    "market_min": 559, "market_min_airline": "沙特航空",
                    "ca_index": 134.5, "ca_vs_min": 193, "comp_avg": 765.7,
                  }]
                }
              ]
            }
          }
        }
    """
    # ── Filter flights ────────────────────────────────────────────────────────
    flights = _normalize_currency(flights)
    flights = [f for f in flights
               if int(f.get("stops", 0)) <= MAX_STOPS
               and not _has_excessive_layover(f)]

    for f in flights:
        if "category" not in f:
            f["category"] = classify_stop_type(f)
        if "type_display" not in f:
            f["type_display"] = CATEGORY_DISPLAY.get(f["category"], f["category"])

    if cabin_filter:
        flights = [f for f in flights if f["cabin"] in cabin_filter]
    if type_filter:
        flights = [f for f in flights if f.get("type_display") in type_filter]

    # ── Period assignment ─────────────────────────────────────────────────────
    period_order: dict[str, int] = {}

    # Pre-parse range boundaries once for performance
    parsed_ranges = (
        [(dt_date.fromisoformat(r["start"]), dt_date.fromisoformat(r["end"]),
          f"{r['start']} | {r['end']}")
         for r in date_ranges]
        if date_ranges else []
    )

    def _get_period(date_str: str) -> str:
        d = dt_date.fromisoformat(date_str)
        # 1. Exact range match (normal path)
        for s, e, key in parsed_ranges:
            if s <= d <= e:
                if key not in period_order:
                    period_order[key] = len(period_order)
                return key
        # 2. Nearest-range fallback — never silently drop a flight.
        #    Flights from reports with no date_ranges (single-route searches,
        #    different week searches) are assigned to the closest period by
        #    distance from its boundaries.  Ties: prefer the earlier range.
        if parsed_ranges:
            best_key = min(
                parsed_ranges,
                key=lambda t: min(abs((d - t[0]).days), abs((d - t[1]).days)),
            )[2]
            if best_key not in period_order:
                period_order[best_key] = len(period_order)
            return best_key
        # 3. No ranges at all — use the date itself as its own period
        if date_str not in period_order:
            period_order[date_str] = len(period_order)
        return date_str

    # ── Group: cabin → route → type → period → {code: min_price} ─────────────
    cells: dict = defaultdict(
        lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    )
    airline_names: dict[str, str] = {}

    for f in flights:
        period = _get_period(f["departure_date"])
        cabin = f["cabin"]
        route = f"{f['origin']}-{f['destination']}"
        type_label = f.get("type_display", "")
        code  = f["airline_code"]
        price = f["price"]
        if price <= 0:
            continue
        airline_names[code] = f.get("airline", code)
        cell = cells[cabin][route][type_label][period]
        if code not in cell or price < cell[code]:
            cell[code] = price

    currency = flights[0]["currency"] if flights else "HKD"
    result: dict[str, Any] = {"currency": currency, "cabins": {}}

    # ── Build per-cabin analytics ─────────────────────────────────────────────
    for cabin in sorted(cells.keys(), key=lambda c: CABIN_ORDER.get(c, 9)):
        routes_data   = cells[cabin]
        total_combos  = 0
        ca_cheapest   = 0
        ca_below_avg  = 0
        ca_above_avg  = 0
        ca_missing    = 0
        ca_indices: list[float] = []
        route_results: list[dict] = []

        for route in sorted(routes_data.keys()):
            for type_label in sorted(routes_data[route].keys(),
                                     key=lambda t: TYPE_ORDER.get(t, 9)):
                periods_data = routes_data[route][type_label]
                periods_list: list[dict] = []

                for period in sorted(periods_data.keys(),
                                     key=lambda p: period_order.get(p, 0)):
                    prices = periods_data[period]
                    total_combos += 1
                    ca_p = prices.get("CA")

                    if ca_p is None:
                        ca_missing += 1

                    all_p = [(c, p) for c, p in prices.items() if p > 0]
                    if not all_p:
                        continue
                    mmin_code, mmin = min(all_p, key=lambda x: x[1])
                    mmin_airline = airline_names.get(mmin_code, mmin_code)

                    ca_index = round(ca_p / mmin * 100, 1) if (ca_p and mmin) else None
                    if ca_index is not None:
                        ca_indices.append(ca_index)

                    ca_vs_min = round(ca_p - mmin, 0) if ca_p is not None else None
                    if ca_vs_min == 0 and ca_p is not None:
                        ca_cheapest += 1

                    comp_p = [p for c, p in prices.items() if c != "CA" and p > 0]
                    comp_avg = round(sum(comp_p) / len(comp_p), 1) if comp_p else None
                    if ca_p is not None and comp_avg is not None:
                        if ca_p < comp_avg:
                            ca_below_avg += 1
                        else:
                            ca_above_avg += 1

                    # BA/VS combined
                    ba_p, vs_p = prices.get("BA"), prices.get("VS")
                    ba_vs = ba_vs_name = None
                    if ba_p is not None and vs_p is not None:
                        ba_vs, ba_vs_name = (ba_p, "BA") if ba_p <= vs_p else (vs_p, "VS")
                    elif ba_p is not None:
                        ba_vs, ba_vs_name = ba_p, "BA"
                    elif vs_p is not None:
                        ba_vs, ba_vs_name = vs_p, "VS"

                    periods_list.append({
                        "period":             period,
                        "ca":                 ca_p,
                        "cz":                 prices.get("CZ"),
                        "mu":                 prices.get("MU"),
                        "ba_vs":              ba_vs,
                        "ba_vs_name":         ba_vs_name,
                        "hu":                 prices.get("HU"),
                        "market_min":         mmin,
                        "market_min_airline": mmin_airline,
                        "ca_index":           ca_index,
                        "ca_vs_min":          ca_vs_min,
                        "comp_avg":           comp_avg,
                    })

                if periods_list:
                    route_results.append({
                        "route":   route,
                        "type":    type_label,
                        "periods": periods_list,
                    })

        denom = ca_below_avg + ca_above_avg
        result["cabins"][cabin] = {
            "label":              CABIN_LABEL.get(cabin, cabin),
            "total_combos":       total_combos,
            "ca_cheapest_count":  ca_cheapest,
            "ca_below_avg_count": ca_below_avg,
            "ca_above_avg_count": ca_above_avg,
            "ca_missing_count":   ca_missing,
            "ca_avg_index":       round(sum(ca_indices) / len(ca_indices), 1) if ca_indices else None,
            "ca_below_avg_pct":   round(ca_below_avg / denom * 100, 1) if denom else 0,
            "routes":             route_results,
        }

    return result
