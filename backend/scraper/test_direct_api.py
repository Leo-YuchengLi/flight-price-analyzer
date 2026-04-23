"""
Test direct API calls to Trip.com's internal flight search endpoint.
Uses a browser session to get cookies, then calls the API via httpx.

Run:  cd backend && python -m scraper.test_direct_api
"""
import asyncio
import json
import logging
import sys
from pathlib import Path

import httpx
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# ── Build search payload ───────────────────────────────────────────────────────

def build_search_payload(
    depart_code: str,
    arrive_code: str,
    depart_date: str,   # YYYY-MM-DD
    depart_airport: str = "",
    arrive_airport: str = "",
    cabin: str = "Y",   # Y=Economy, C=Business, F=First
    currency: str = "USD",
    locale: str = "en-XX",
    cid: str = "09031419111507719498",  # fallback CID
) -> dict:
    """Build the FlightListSearchSSE payload."""
    cabin_map = {"Y": "y", "C": "c", "F": "f"}
    return {
        "mode": 0,
        "searchCriteria": {
            "grade": 3,
            "realGrade": 1,
            "tripType": 1,
            "journeyNo": 1,
            "passengerInfoType": {"adultCount": 1, "childCount": 0, "infantCount": 0},
            "journeyInfoTypes": [{
                "journeyNo": 1,
                "departDate": depart_date,
                "departCode": depart_code.upper(),
                "arriveCode": arrive_code.upper(),
                "departAirport": depart_airport,
                "arriveAirport": arrive_airport,
                "cabinClass": cabin_map.get(cabin, "y"),
            }],
            "policyId": None,
        },
        "sortInfoType": {"direction": True, "orderBy": "Direct", "topList": []},
        "tagList": [],
        "flagList": ["NEED_RESET_SORT", "FullDataCache"],
        "filterType": {
            "filterFlagTypes": [],
            "queryItemSettings": [],
            "studentsSelectedStatus": True,
        },
        "abtList": [
            {"abCode": "250811_IBU_wjrankol", "abVersion": "A"},
            {"abCode": "251023_IBU_pricetool", "abVersion": "E"},
            {"abCode": "260302_IBU_farecardjc", "abVersion": "B"},
        ],
        "head": {
            "cid": cid,
            "ctok": "",
            "cver": "3",
            "lang": "01",
            "sid": "8888",
            "syscode": "40",
            "auth": "",
            "xsid": "",
            "extension": [
                {"name": "source", "value": "ONLINE"},
                {"name": "sotpGroup", "value": "Trip"},
                {"name": "sotpLocale", "value": locale},
                {"name": "sotpCurrency", "value": currency},
                {"name": "allianceID", "value": "0"},
                {"name": "sid", "value": "0"},
                {"name": "ouid", "value": ""},
                {"name": "uuid"},
                {"name": "useDistributionType", "value": "1"},
                {"name": "x-ua", "value": "v=3_os=ONLINE_osv=10.15.7"},
                {"name": "PageId", "value": "10320667452"},
                {"name": "xproduct", "value": "baggage"},
                {"name": "units", "value": "METRIC"},
                {"name": "sotpUnit", "value": "METRIC"},
            ],
            "Locale": locale,
            "Language": "en",
            "Currency": currency,
            "ClientID": "",
            "appid": "700020",
        },
    }


# ── SSE parser ────────────────────────────────────────────────────────────────

def parse_sse_event(chunk: str) -> list[dict]:
    """Parse a chunk of SSE text and return any JSON data payloads."""
    events = []
    for block in chunk.split("\n\n"):
        data_lines = [l[5:] for l in block.splitlines() if l.startswith("data:")]
        for line in data_lines:
            line = line.strip()
            if not line or line == "[DONE]":
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return events


# ── Flight extractor from SSE events ──────────────────────────────────────────

def extract_flights_from_sse(events: list[dict], origin: str, dest: str,
                              date: str, cabin: str, currency: str) -> list[dict]:
    """
    Parse Trip.com SSE events and extract flight info.
    The events may contain 'flightItineraryList', 'data', or nested structures.
    """
    from datetime import datetime
    flights = []
    seen_ids = set()

    def _parse_item(item: dict) -> dict | None:
        try:
            # Extract journey / segment info
            segs_raw = (item.get("flightSegments")
                        or item.get("segments")
                        or item.get("journeySegments")
                        or [])
            segs = []
            for s in segs_raw:
                seg_origin = s.get("departureCityCode") or s.get("dCity") or s.get("departCity", origin)
                seg_dest = s.get("arrivalCityCode") or s.get("aCity") or s.get("arriveCity", dest)
                segs.append({
                    "airline":        s.get("airlineName") or s.get("marketFlightCompanyName", ""),
                    "airline_code":   s.get("airlineCode") or s.get("marketFlightCompanyCode", ""),
                    "flight_number":  s.get("flightNumber") or s.get("flightNo", ""),
                    "origin":         seg_origin,
                    "destination":    seg_dest,
                    "departure_time": s.get("departureTime") or s.get("departTime", ""),
                    "arrival_time":   s.get("arrivalTime") or s.get("arriveTime", ""),
                    "departure_date": s.get("departureDate") or s.get("dDate", date),
                    "arrival_date":   s.get("arrivalDate") or s.get("aDate", date),
                    "aircraft":       s.get("aircraftTypeName") or s.get("aircraftType", ""),
                })

            # Price
            prices = (item.get("priceList")
                      or item.get("adultPriceList")
                      or item.get("fareList")
                      or [])
            price_obj = prices[0] if prices else {}
            price = float(
                price_obj.get("salePrice")
                or price_obj.get("adultPrice")
                or price_obj.get("price")
                or item.get("minPrice")
                or item.get("price", 0)
            )

            stops = int(item.get("transferCount") or item.get("stopCount", max(0, len(segs) - 1)))
            airline = item.get("mainAirlineName") or item.get("airlineName") or (segs[0]["airline"] if segs else "")
            airline_code = item.get("mainAirlineCode") or item.get("airlineCode") or (segs[0]["airline_code"] if segs else "")

            dur_min = item.get("totalDuration") or item.get("durationInMinutes") or 0
            h, m = divmod(int(dur_min), 60)
            dur_str = f"{h}h {m:02d}m" if dur_min else ""

            # Dedup by flight number + departure time
            uid = f"{airline_code}-{segs[0]['flight_number'] if segs else ''}-{segs[0]['departure_time'] if segs else ''}"
            if uid in seen_ids:
                return None
            seen_ids.add(uid)

            return {
                "origin": origin,
                "destination": dest,
                "departure_date": date,
                "trip_type": "one_way",
                "segments": segs,
                "stops": stops,
                "is_direct": stops == 0,
                "total_duration": dur_str,
                "airline": airline,
                "airline_code": airline_code,
                "price": price,
                "currency": currency,
                "cabin": cabin,
                "scraped_at": datetime.now().isoformat(),
                "source_url": "trip.com",
            }
        except Exception as exc:
            logger.debug("Failed to parse item: %s", exc)
            return None

    for event in events:
        # Try common response structures
        for path in [
            ["data", "flightItineraryList"],
            ["data", "flightList"],
            ["data", "journeyList"],
            ["flightItineraryList"],
            ["flightList"],
            ["journeyList"],
            ["ResponseBody", "flightItineraryList"],
        ]:
            obj = event
            for key in path:
                obj = obj.get(key) if isinstance(obj, dict) else None
                if obj is None:
                    break
            if isinstance(obj, list) and obj:
                for item in obj:
                    parsed = _parse_item(item)
                    if parsed:
                        flights.append(parsed)

    return flights


# ── Main test function ────────────────────────────────────────────────────────

async def test_direct_api(
    origin: str = "LON",
    dest: str = "BJS",
    date: str = "2026-06-15",
    cabin: str = "Y",
    currency: str = "USD",
):
    logger.info("Testing direct API: %s → %s on %s", origin, dest, date)

    # ── Step 1: Get session cookies from browser ────────────────────────────
    logger.info("Step 1: Getting session cookies from browser...")
    session_cookies = {}
    cid = "09031419111507719498"

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel="chrome",
            headless=True,
            args=["--window-size=1280,800"],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="en-HK",
            timezone_id="Asia/Hong_Kong",
        )
        page = await context.new_page()

        # Just load the homepage to get session cookies
        await page.goto("https://www.trip.com/flights/", wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(2000)

        # Extract cookies
        cookies = await context.cookies()
        for c in cookies:
            session_cookies[c["name"]] = c["value"]
        logger.info("Got %d cookies: %s", len(session_cookies), list(session_cookies.keys())[:10])

        # Extract CID from page
        cid_val = await page.evaluate("""
        () => {
            // CID is in cookies or sessionStorage
            const cookies = document.cookie.split(';');
            for (const c of cookies) {
                if (c.trim().startsWith('_ga=') || c.trim().startsWith('cid=')) {
                    return c.trim();
                }
            }
            return null;
        }
        """)

        # Extract from cookies dict
        if "nfes_pwa_uid" in session_cookies:
            cid = session_cookies["nfes_pwa_uid"]
        elif "cid" in session_cookies:
            cid = session_cookies["cid"]
        logger.info("CID: %s", cid)

        await browser.close()

    # ── Step 2: Call FlightListSearchSSE directly ────────────────────────────
    logger.info("Step 2: Calling FlightListSearchSSE API...")

    payload = build_search_payload(
        depart_code=origin,
        arrive_code=dest,
        depart_date=date,
        cabin=cabin,
        currency=currency,
        cid=cid,
    )

    headers = {
        "Accept": "text/event-stream",
        "Content-Type": "application/json",
        "Origin": "https://www.trip.com",
        "Referer": f"https://www.trip.com/flights/showfarefirst?dcity={origin.lower()}&acity={dest.lower()}&ddate={date}&triptype=ow&class={cabin.lower()}&quantity=1&nonstoponly=off&locale=en-XX&curr={currency}",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "x-traceID": "test-trace-001",
    }

    all_events = []
    all_flights = []
    raw_sse_lines = []

    try:
        async with httpx.AsyncClient(
            cookies=session_cookies,
            timeout=httpx.Timeout(60.0),
            follow_redirects=True,
        ) as client:
            async with client.stream(
                "POST",
                "https://www.trip.com/restapi/soa2/27015/FlightListSearchSSE",
                json=payload,
                headers=headers,
            ) as resp:
                logger.info("Response status: %d", resp.status_code)
                logger.info("Response headers: %s", dict(resp.headers))

                buffer = ""
                async for chunk in resp.aiter_text():
                    buffer += chunk
                    raw_sse_lines.append(chunk[:200])

                    # Parse complete SSE events
                    events = parse_sse_event(buffer)
                    if events:
                        all_events.extend(events)
                        for ev in events:
                            keys = list(ev.keys()) if isinstance(ev, dict) else str(ev)[:50]
                            logger.info("  SSE event keys: %s", keys)
                        buffer = ""  # reset after parsing

                logger.info("Total SSE chunks: %d, events: %d", len(raw_sse_lines), len(all_events))

    except Exception as exc:
        logger.error("API call failed: %s", exc)

    # ── Step 3: Parse flights from events ────────────────────────────────────
    logger.info("Step 3: Parsing flights...")
    flights = extract_flights_from_sse(all_events, origin, dest, date, cabin, currency)
    logger.info("Parsed %d flights", len(flights))

    # Save raw events for analysis
    out = {
        "origin": origin,
        "dest": dest,
        "date": date,
        "status": "ok" if flights else "no_flights",
        "event_count": len(all_events),
        "flight_count": len(flights),
        "raw_events_sample": all_events[:3] if all_events else [],
        "flights": flights[:5] if flights else [],
        "raw_sse_sample": raw_sse_lines[:10],
    }
    out_path = Path(__file__).parent / "direct_api_test.json"
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    logger.info("Results saved to: %s", out_path)

    # Print summary
    if flights:
        print(f"\n{'='*60}")
        print(f"Found {len(flights)} flights from {origin} to {dest} on {date}:")
        for f in flights[:10]:
            print(f"  {f['airline']} {f.get('segments', [{}])[0].get('flight_number','')} "
                  f"dep:{f.get('segments', [{}])[0].get('departure_time','')} "
                  f"arr:{f.get('segments', [{}])[0].get('arrival_time','')} "
                  f"stops:{f['stops']} "
                  f"price:{f['price']:.0f} {f['currency']}")
    else:
        print("\nNo flights parsed. Examining raw SSE events:")
        for i, ev in enumerate(all_events[:5]):
            print(f"\nEvent {i}: {json.dumps(ev, ensure_ascii=False)[:500]}")
        if raw_sse_lines:
            print("\nRaw SSE sample:")
            for line in raw_sse_lines[:5]:
                print(f"  {line[:300]}")

    return flights


if __name__ == "__main__":
    origin = sys.argv[1] if len(sys.argv) > 1 else "LON"
    dest = sys.argv[2] if len(sys.argv) > 2 else "BJS"
    date = sys.argv[3] if len(sys.argv) > 3 else "2026-06-15"
    asyncio.run(test_direct_api(origin, dest, date))
