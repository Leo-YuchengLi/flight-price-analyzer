"""
Flight scraper — uses a real browser to navigate hk.trip.com's showfarefirst URL
and captures the complete FlightListSearchSSE response body.

Why browser instead of raw httpx:
  The SSE response is ~400-500 KB and arrives in a single large JSON event.
  Direct httpx calls receive a truncated response (~14-18 results).
  A real browser session receives the full 90+ result set.

dry_run=True → mock data (no network).
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
from datetime import datetime
from typing import Callable

from playwright.async_api import async_playwright, BrowserContext

try:
    from playwright_stealth import stealth_async
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False

logger = logging.getLogger(__name__)


# ── Mock data (dry_run) ───────────────────────────────────────────────────────

def _make_mock(origin: str, destination: str, date: str,
               cabin: str, currency: str) -> list[dict]:
    airlines = [
        ("Air China",       "CA", "CA855",  "10:30", "06:15", "11h 45m"),
        ("China Eastern",   "MU", "MU551",  "13:45", "08:30", "10h 45m"),
        ("China Southern",  "CZ", "CZ303",  "15:00", "09:00", "10h 00m"),
        ("British Airways", "BA", "BA039",  "21:30", "17:15", "11h 45m"),
        ("KLM",             "KL", "KL887",  "11:30", "09:00", "13h 30m"),
        ("Air France",      "AF", "AF182",  "14:00", "10:30", "12h 30m"),
        ("Emirates",        "EK", "EK009",  "21:55", "17:00", "12h 05m"),
        ("Qatar Airways",   "QR", "QR017",  "09:15", "04:35", "11h 20m"),
    ]
    base = {"Y": random.uniform(420, 680), "C": random.uniform(1800, 3200),
            "F": random.uniform(5000, 9000)}.get(cabin, 500)
    results = []
    for airline, code, fnum, dep, arr, dur in airlines:
        stops = 0 if code in ("CA", "BA") else 1
        results.append({
            "origin": origin, "destination": destination, "departure_date": date,
            "trip_type": "one_way",
            "segments": [{"airline": airline, "airline_code": code, "flight_number": fnum,
                          "origin": origin, "destination": destination,
                          "departure_time": dep, "arrival_time": arr,
                          "departure_date": date, "arrival_date": date,
                          "aircraft": "Boeing 777"}],
            "stops": stops, "is_direct": stops == 0, "total_duration": dur,
            "airline": airline, "airline_code": code,
            "price": round(base * random.uniform(0.85, 1.25), 2),
            "currency": currency, "cabin": cabin,
            "scraped_at": datetime.now().isoformat(), "source_url": "mock://dry_run",
        })
    results.sort(key=lambda r: r["price"])
    return results


# ── SSE parser ────────────────────────────────────────────────────────────────

def _parse_sse_events(body: str, origin: str, dest: str, date: str,
                      cabin: str, currency: str) -> list[dict]:
    """Parse the complete SSE body → flight list."""
    events: list[dict] = []
    for block in body.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data:"):
                try:
                    events.append(json.loads(line[5:].strip()))
                except json.JSONDecodeError:
                    pass

    flights: list[dict] = []
    seen: set[str] = set()

    for ev in events:
        airline_map = {a["code"]: a["name"]
                       for a in ev.get("airlineList") or []
                       if a.get("code")}
        for item in ev.get("itineraryList") or []:
            journey = (item.get("journeyList") or [{}])[0]
            sections = journey.get("transSectionList") or []
            if not sections:
                continue

            segs = []
            for s in sections:
                dep_pt = s.get("departPoint") or {}
                arr_pt = s.get("arrivePoint") or {}
                fi = s.get("flightInfo") or {}
                craft = fi.get("craftInfo") or {}
                dep_dt = s.get("departDateTime", "")
                arr_dt = s.get("arriveDateTime", "")

                # Use actualAirlineCode (marketing/codeshare carrier) when available,
                # e.g. LH7322 operated by LH but sold as CA966 → actualAirlineCode=CA
                op_code     = fi.get("airlineCode", "")
                actual_code = fi.get("actualAirlineCode") or op_code
                share_fno   = fi.get("shareFlightNo") or ""
                flight_no   = share_fno or fi.get("flightNo", "")

                segs.append({
                    "airline":          airline_map.get(actual_code, actual_code),
                    "airline_code":     actual_code,
                    "operating_code":   op_code,   # keep for reference
                    "flight_number":    flight_no,
                    "origin":           dep_pt.get("cityCode", origin),
                    "destination":      arr_pt.get("cityCode", dest),
                    "departure_time":   dep_dt[11:16] if len(dep_dt) >= 16 else dep_dt,
                    "arrival_time":     arr_dt[11:16] if len(arr_dt) >= 16 else arr_dt,
                    "departure_date":   dep_dt[:10]   if len(dep_dt) >= 10 else date,
                    "arrival_date":     arr_dt[:10]   if len(arr_dt) >= 10 else date,
                    "aircraft":         craft.get("shortName") or craft.get("name", ""),
                })

            policies = item.get("policies") or []
            price_obj = (policies[0].get("price") or {}) if policies else {}
            adult = price_obj.get("adult") or {}
            # adult.totalPrice = salePrice + tax = the blue "you pay" price shown on Trip.com
            # We always use the discounted total (incl. taxes), NOT the strikethrough original
            price = float(
                adult.get("totalPrice")
                or price_obj.get("totalPrice")
                or adult.get("salePrice")
                or 0
            )

            dur_min = journey.get("duration") or 0
            h, m = divmod(int(dur_min), 60)
            stops = max(0, len(sections) - 1)
            main_code = segs[0]["airline_code"] if segs else ""
            main_name = segs[0]["airline"] if segs else ""

            # Build a dedup key from airline+flight codes.
            # Fallback: if all codes are empty (some Trip.com responses omit them),
            # use departure times so we don't collapse all flights into one entry.
            uid = "|".join(f"{s['airline_code']}{s['flight_number']}" for s in segs)
            if not uid.replace("|", ""):
                uid = "t|" + "|".join(
                    f"{s.get('departure_date','')}{s.get('departure_time','')}"
                    for s in segs
                )
            if uid in seen:
                continue
            seen.add(uid)

            flights.append({
                "origin": origin, "destination": dest, "departure_date": date,
                "trip_type": "one_way",
                "segments": segs, "stops": stops, "is_direct": stops == 0,
                "total_duration": f"{h}h {m:02d}m" if dur_min else "",
                "airline": main_name, "airline_code": main_code,
                "price": price, "currency": currency, "cabin": cabin,
                "scraped_at": datetime.now().isoformat(), "source_url": "hk.trip.com",
            })

    return sorted(flights, key=lambda f: f["price"])


# ── Main scraper class ────────────────────────────────────────────────────────

class TripScraper:
    """
    Browser-based scraper for hk.trip.com.

    Strategy:
      1. start()  — launch Chromium, load hk.trip.com homepage (establishes session).
      2. scrape_one() — navigate to showfarefirst URL, intercept the full
                        FlightListSearchSSE response body (400-500 KB, ~90+ flights).
      3. Parse SSE body with _parse_sse_events().

    One persistent browser instance; a fresh page per search.
    """

    # Refresh the browser context after this many route searches to prevent
    # accumulated cookies/cache from degrading SSE capture quality
    _CONTEXT_REFRESH_EVERY = 2

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._pw = None
        self._browser = None
        self._context: BrowserContext | None = None
        self._route_count = 0   # tracks unique origins served since last refresh
        # Concurrency guards:
        #   _page_sem — max 2 simultaneous pages open at once
        #   _ctx_lock — serialise context refresh
        self._page_sem = asyncio.Semaphore(2)
        self._ctx_lock = asyncio.Lock()

    async def start(self) -> None:
        logger.info("TripScraper: launching browser…")
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless=self.headless,
            args=["--no-sandbox", "--disable-gpu", "--window-size=1400,900"],
        )
        self._context = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1400, "height": 900},
            locale="en-HK",
            timezone_id="Asia/Hong_Kong",
            extra_http_headers={"Accept-Language": "en-HK,en-GB;q=0.9,en;q=0.8"},
        )

        # Warm-up: load homepage to establish session cookies
        page = await self._context.new_page()
        if HAS_STEALTH:
            await stealth_async(page)
        await page.goto("https://hk.trip.com/", wait_until="domcontentloaded", timeout=25000)
        await asyncio.sleep(2.5)
        await page.close()
        logger.info("TripScraper ready")

    async def stop(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
        self._browser = None
        logger.info("TripScraper stopped")

    async def refresh_context(self) -> None:
        """Close and recreate the browser context to clear accumulated state.
        Call this between route groups in large batch searches to prevent
        context bloat from degrading SSE capture quality.
        Serialised by _ctx_lock so concurrent scrape_one calls never race here.
        """
        if not self._browser:
            return
        async with self._ctx_lock:
            if self._context:
                try:
                    await self._context.close()
                except Exception:
                    pass

        self._context = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1400, "height": 900},
            locale="en-HK",
            timezone_id="Asia/Hong_Kong",
            extra_http_headers={"Accept-Language": "en-HK,en-GB;q=0.9,en;q=0.8"},
        )
        # Brief warm-up
        page = await self._context.new_page()
        if HAS_STEALTH:
            await stealth_async(page)
        await page.goto("https://hk.trip.com/", wait_until="domcontentloaded", timeout=25000)
        await asyncio.sleep(2.0)
        await page.close()
        logger.info("TripScraper: context refreshed")

    async def scrape_one(
        self,
        origin: str,
        destination: str,
        date: str,
        cabin: str = "Y",
        currency: str = "HKD",
        trip_type: str = "one_way",
        dry_run: bool = False,
        on_progress: Callable[[str], None] | None = None,
    ) -> list[dict]:
        if dry_run:
            await asyncio.sleep(random.uniform(0.3, 0.8))
            return _make_mock(origin, destination, date, cabin, currency)

        assert self._browser, "Call start() first"

        if on_progress:
            on_progress(f"Scraping {origin}→{destination} {date}…")

        cabin_map = {"Y": "y", "C": "c", "F": "f"}
        search_url = (
            f"https://hk.trip.com/flights/showfarefirst"
            f"?dcity={origin.lower()}&acity={destination.lower()}&ddate={date}"
            f"&triptype=ow&class={cabin_map.get(cabin, 'y')}&quantity=1"
            f"&nonstoponly=off&locale=en-HK&curr={currency}"
        )

        # Limit concurrent pages to 2 while allowing parallel route searches.
        async with self._page_sem:
            page = await self._context.new_page()
        if HAS_STEALTH:
            await stealth_async(page)

        # Accumulate ALL FlightListSearchSSE responses (Trip.com sometimes sends
        # a quick first response with only 1 result, then a full response seconds later)
        sse_bodies: list[str] = []
        sse_done = asyncio.Event()

        async def on_response(resp):
            if "FlightListSearchSSE" not in resp.url:
                return
            try:
                raw = await resp.body()
                body = raw.decode("utf-8", errors="replace")
                sse_bodies.append(body)
                logger.debug("SSE response #%d: %d bytes", len(sse_bodies), len(raw))
                if not sse_done.is_set():
                    sse_done.set()
            except Exception as exc:
                logger.warning("SSE body read failed: %s", exc)
                if not sse_done.is_set():
                    sse_done.set()

        page.on("response", on_response)

        try:
            logger.info("Navigating: %s", search_url[:100])
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)

            # Wait for the first SSE response (up to 30 s).
            try:
                await asyncio.wait_for(sse_done.wait(), timeout=30.0)
                # Small first response (≤ 50 KB) = partial/initial result — wait
                # up to 10 more seconds for the full response to arrive.
                # Large responses are complete immediately → 1 s settle is enough.
                if sse_bodies and len(sse_bodies[-1]) < 50_000:
                    logger.debug("Small SSE body (%d B) — waiting for full response…",
                                 len(sse_bodies[-1]))
                    await asyncio.sleep(10.0)
                else:
                    await asyncio.sleep(1.0)
            except asyncio.TimeoutError:
                logger.warning("SSE response not captured within 30 s for %s→%s %s",
                               origin, destination, date)

            logger.info("Final URL: %s | SSE bodies: %s",
                        page.url[:80], [len(b) for b in sse_bodies])

        except Exception as exc:
            logger.error("scrape_one error: %s", exc)
        finally:
            await page.close()
            await asyncio.sleep(random.uniform(2.0, 4.0))   # polite delay

        if not sse_bodies:
            logger.warning("No SSE body captured for %s→%s %s", origin, destination, date)
            return []

        full_body = "\n\n".join(sse_bodies)
        flights = _parse_sse_events(full_body, origin, destination, date, cabin, currency)
        logger.info("Scraped %d flights for %s→%s %s (from %d SSE response(s))",
                    len(flights), origin, destination, date, len(sse_bodies))
        return flights
