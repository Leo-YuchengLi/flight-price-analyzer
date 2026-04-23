"""
hk.trip.com full-browser scraper.
Strategy: simulate real user interaction → capture internal API response.
Uses playwright-stealth + human-like behaviour on the lower-anti-bot HK site.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
from datetime import datetime, date as dt_date
from typing import Callable

from playwright.async_api import async_playwright, Page, BrowserContext

try:
    from playwright_stealth import stealth_async
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False
    logging.warning("playwright-stealth not found — install it: pip install playwright-stealth")

logger = logging.getLogger(__name__)

# ── Human behaviour helpers ───────────────────────────────────────────────────

async def _pause(mn=0.8, mx=2.5):
    await asyncio.sleep(random.uniform(mn, mx))


async def _human_type(page: Page, text: str):
    for ch in text:
        await page.keyboard.type(ch)
        await asyncio.sleep(random.uniform(0.05, 0.15))


# ── City input ────────────────────────────────────────────────────────────────

async def _fill_city(page: Page, test_id: str, text: str) -> bool:
    """Click city input, type text, select first autocomplete result."""
    try:
        # Use JS click to bypass any invisible overlays
        await page.evaluate(f"""
        () => {{
            const el = document.querySelector('[data-testid="{test_id}"]');
            if (el) {{ el.focus(); el.click(); }}
        }}
        """)
        await _pause(0.4, 0.8)

        # Clear and type
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Delete")
        await _human_type(page, text)
        await _pause(1.2, 2.0)  # wait for autocomplete

        # Select first item from dropdown
        item_sels = [
            ".m-flight-poi-list li",
            "[class*='poi-list'] li",
            "[class*='poi'] [class*='item']",
            "[class*='suggest'] li",
        ]
        for sel in item_sels:
            items = page.locator(sel)
            if await items.count() > 0:
                await items.first.click()
                logger.debug("  %s → selected '%s'", test_id, text)
                await _pause(0.4, 0.8)
                # Dismiss dropdown
                await page.keyboard.press("Escape")
                await _pause(0.3, 0.5)
                return True

        await page.keyboard.press("Enter")
        await _pause(0.3, 0.6)
        return True
    except Exception as exc:
        logger.warning("  _fill_city(%s, %s): %s", test_id, text, exc)
        return False


# ── Date picker ───────────────────────────────────────────────────────────────

async def _open_date_picker(page: Page) -> bool:
    """Click the date picker container to open the calendar."""
    opened = await page.evaluate("""
    () => {
        // Try clicking the date LI wrapper
        const candidates = [
            document.querySelector('.m-searchForm__item.segment-date'),
            document.querySelector('[class*="segment-date"]'),
            document.querySelector('[class*="m-searchForm__item"][class*="date"]'),
            document.querySelector('[data-testid="search_date_depart0"]')?.closest('li'),
            document.querySelector('[data-testid="search_date_depart0"]')?.parentElement,
        ].filter(Boolean);

        for (const el of candidates) {
            el.click();
            const cal = document.querySelector(
                '[class*="m-calendar"], [class*="nh_d-"], [class*="datepicker"], [class*="calendar"]'
            );
            if (cal) return { ok: true, clicked: el.className.slice(0, 60) };
        }
        return { ok: false };
    }
    """)
    logger.debug("  Date picker open: %s", opened)
    await _pause(0.6, 1.2)
    return opened.get("ok", False)


async def _get_calendar_months(page: Page) -> list[str]:
    """Return visible month/year headers from the open calendar."""
    return await page.evaluate("""
    () => {
        const sels = [
            '[class*="nh_d-monthTitle"]',
            '[class*="m-calendar-title"]',
            '[class*="calendar"] [class*="title"]',
            '[class*="calendar"] [class*="month"]',
            '[class*="dateHeader"]',
        ];
        const seen = new Set();
        for (const s of sels) {
            document.querySelectorAll(s).forEach(el => {
                const t = el.innerText?.trim();
                if (t && t.length > 2 && t.length < 50) seen.add(t);
            });
        }
        return [...seen];
    }
    """)


async def _click_next_month(page: Page) -> bool:
    """Advance calendar one month forward."""
    result = await page.evaluate("""
    () => {
        // Look for next/forward arrow in calendar header area
        const nextSels = [
            '[class*="nh_d-nextBtn"]', '[class*="nh_d-next"]',
            '[class*="nextBtn"]',     '[class*="next-btn"]',
            '[class*="next-month"]',  '[class*="nextMonth"]',
            '[class*="arrowRight"]',  '[class*="arrow-right"]',
            '[class*="forward"]',
        ];
        for (const sel of nextSels) {
            const el = document.querySelector(sel);
            if (el) { el.click(); return { ok: true, sel }; }
        }

        // Fallback: find elements with arrow-like text (›, >, →, >>)
        const all = Array.from(document.querySelectorAll(
            '[class*="calendar"] *, [class*="datepicker"] *, [class*="nh_d-"] *'
        ));
        const arrows = all.filter(el => {
            const t = el.innerText?.trim();
            return ['›', '>', '→', '»', '▶'].includes(t) && el.offsetParent;
        });
        if (arrows.length > 0) {
            // Pick the one furthest to the right
            arrows.sort((a, b) => b.getBoundingClientRect().right - a.getBoundingClientRect().right);
            arrows[0].click();
            return { ok: true, sel: 'arrow-text', text: arrows[0].innerText };
        }

        // Last resort: inspect ALL elements in calendar for onclick/cursor:pointer
        const clickable = Array.from(document.querySelectorAll(
            '[class*="calendar"] *, [class*="nh_d-"] *'
        )).filter(el => {
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.cursor === 'pointer' && rect.width < 50 && rect.height < 50 && rect.width > 0;
        });
        // Right-most small clickable element
        clickable.sort((a, b) => b.getBoundingClientRect().right - a.getBoundingClientRect().right);
        if (clickable.length > 0) {
            clickable[0].click();
            return { ok: true, sel: 'cursor-pointer-rightmost', class: clickable[0].className };
        }

        return { ok: false };
    }
    """)
    logger.debug("  next-month: %s", result)
    await _pause(0.4, 0.8)
    return result.get("ok", False)


async def _click_day(page: Page, day: int) -> bool:
    """Click a day number in the open calendar."""
    result = await page.evaluate(f"""
    () => {{
        const target = '{day}';
        const sels = [
            '[class*="nh_d-dayText"]',
            '[class*="calendar"] td',
            '[class*="calendar"] [class*="day"]',
            '[class*="datepicker"] td',
        ];
        for (const sel of sels) {{
            const cells = Array.from(document.querySelectorAll(sel));
            for (const cell of cells) {{
                const t = cell.innerText?.trim();
                if (t === target) {{
                    const cls = (cell.className || '').toLowerCase();
                    if (cls.includes('disable') || cls.includes('gray') || cls.includes('past')) continue;
                    if (cell.getAttribute('aria-disabled') === 'true') continue;
                    cell.click();
                    return {{ ok: true, sel, day: t }};
                }}
            }}
        }}
        return {{ ok: false, target }};
    }}
    """)
    logger.debug("  click day %d: %s", day, result)
    await _pause(0.3, 0.6)
    return result.get("ok", False)


async def _set_date(page: Page, date_str: str) -> bool:
    """Full calendar interaction: open → navigate → click day."""
    import calendar as cal_mod
    target = dt_date.fromisoformat(date_str)

    # Inspect current DOM of the date picker to understand structure
    dom_info = await page.evaluate("""
    () => {
        const dateLi = document.querySelector('.m-searchForm__item.segment-date') ||
                       document.querySelector('[class*="segment-date"]');
        if (!dateLi) return { found: false };
        return {
            found: true,
            tag: dateLi.tagName,
            class: dateLi.className.slice(0, 80),
            children: Array.from(dateLi.children).map(c => ({ tag: c.tagName, class: c.className.slice(0, 50) })),
        };
    }
    """)
    logger.debug("  Date LI info: %s", dom_info)

    # Open the calendar
    await _open_date_picker(page)
    await _pause(0.5, 1.0)

    # Take a snapshot of the calendar DOM for debugging
    cal_dom = await page.evaluate("""
    () => {
        const cal = document.querySelector('[class*="nh_d-"], [class*="m-calendar"], [class*="datepicker"]');
        if (!cal) return { found: false };
        return {
            found: true,
            class: cal.className.slice(0, 80),
            html: cal.outerHTML.slice(0, 800),
        };
    }
    """)
    logger.debug("  Calendar DOM: %s", cal_dom.get("class", "not found"))

    # Navigate to target month
    for attempt in range(30):
        headers = await _get_calendar_months(page)
        logger.debug("  [%d] Calendar headers: %s", attempt, headers)

        month_name = cal_mod.month_name[target.month]
        short_month = cal_mod.month_abbr[target.month]
        on_target = any(
            (month_name in h or short_month in h) and str(target.year) in h
            for h in headers
        )
        if on_target:
            logger.debug("  Found target month: %s %d", month_name, target.year)
            break

        if not await _click_next_month(page):
            logger.warning("  Could not advance calendar after %d tries", attempt)
            # Try screenshot to debug
            try:
                await page.screenshot(path=f"/tmp/cal_stuck_{attempt}.png")
            except Exception:
                pass
            return False
    else:
        return False

    # Click the day
    return await _click_day(page, target.day)


# ── Response parser (same structure as www.trip.com API) ─────────────────────

def _parse_response(body: str, origin: str, dest: str, date: str,
                    cabin: str, currency: str) -> list[dict]:
    """Parse Trip.com itineraryList response into flight dicts."""
    flights = []
    seen: set[str] = set()

    try:
        data = json.loads(body) if isinstance(body, str) else body
    except json.JSONDecodeError:
        return []

    airline_map = {a["code"]: a["name"] for a in data.get("airlineList") or [] if a.get("code")}

    for item in data.get("itineraryList") or []:
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
            code = fi.get("airlineCode", "")
            segs.append({
                "airline":        airline_map.get(code, code),
                "airline_code":   code,
                "flight_number":  fi.get("flightNo", ""),
                "origin":         dep_pt.get("cityCode", origin),
                "destination":    arr_pt.get("cityCode", dest),
                "departure_time": dep_dt[11:16] if len(dep_dt) >= 16 else dep_dt,
                "arrival_time":   arr_dt[11:16] if len(arr_dt) >= 16 else arr_dt,
                "departure_date": dep_dt[:10] if len(dep_dt) >= 10 else date,
                "arrival_date":   arr_dt[:10] if len(arr_dt) >= 10 else date,
                "aircraft":       craft.get("shortName") or craft.get("name", ""),
            })

        policies = item.get("policies") or []
        price_obj = (policies[0].get("price") or {}) if policies else {}
        adult = price_obj.get("adult") or {}
        price = float(adult.get("totalPrice") or price_obj.get("totalPrice") or adult.get("salePrice") or 0)

        dur_min = journey.get("duration") or 0
        h, m = divmod(int(dur_min), 60)
        stops = max(0, len(sections) - 1)
        main_code = segs[0]["airline_code"] if segs else ""
        main_name = segs[0]["airline"] if segs else ""

        uid = "|".join(f"{s['airline_code']}{s['flight_number']}" for s in segs)
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


# ── Main scraper ──────────────────────────────────────────────────────────────

class HKTripScraper:
    """
    Full browser simulation on hk.trip.com.
    One browser instance; one page per search (context reused for cookies).
    """

    def __init__(self, headless: bool = True, currency: str = "HKD"):
        self.headless = headless
        self.currency = currency
        self._pw = None
        self._browser = None
        self._context: BrowserContext | None = None

    async def start(self) -> None:
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            channel="chrome",
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--window-size=1400,900",
                "--no-sandbox",
                "--disable-gpu",
            ],
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
            extra_http_headers={
                "Accept-Language": "en-HK,en-GB;q=0.9,en;q=0.8",
            },
        )
        if HAS_STEALTH:
            # Warm up a page to apply stealth once
            warmup = await self._context.new_page()
            await stealth_async(warmup)
            await warmup.close()

        # Pre-load the homepage to establish cookies
        page = await self._context.new_page()
        if HAS_STEALTH:
            await stealth_async(page)
        logger.info("Loading hk.trip.com homepage for session cookies…")
        await page.goto("https://hk.trip.com/", wait_until="domcontentloaded", timeout=25000)
        await _pause(2, 3)
        logger.info("Homepage loaded: %s", page.url)
        await page.close()

    async def stop(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()

    async def scrape_one(
        self,
        origin: str,
        destination: str,
        date: str,
        cabin: str = "Y",
        currency: str | None = None,
        trip_type: str = "one_way",
        dry_run: bool = False,
        on_progress: Callable[[str], None] | None = None,
    ) -> list[dict]:
        from scraper.trip_scraper import _make_mock
        if dry_run:
            await asyncio.sleep(random.uniform(0.3, 0.8))
            return _make_mock(origin, destination, date, cabin, currency or self.currency)

        curr = currency or self.currency
        if on_progress:
            on_progress(f"Scraping {origin}→{destination} {date}…")

        assert self._browser, "Call start() first"
        page = await self._context.new_page()
        if HAS_STEALTH:
            await stealth_async(page)

        captured: list[dict] = []

        async def on_response(resp):
            ct = resp.headers.get("content-type", "")
            if "json" not in ct:
                return
            url = resp.url
            if "FlightListSearch" not in url and "itinerary" not in url.lower():
                return
            try:
                body = await resp.json()
                if not isinstance(body, dict):
                    return
                flights = _parse_response(body, origin, destination, date, cabin, curr)
                if flights:
                    captured.extend(flights)
                    logger.info("  Captured %d flights from %s", len(flights), url[:80])
            except Exception:
                pass

        page.on("response", on_response)

        try:
            logger.info("Navigating to hk.trip.com/flights/…")
            await page.goto("https://hk.trip.com/flights/", wait_until="domcontentloaded", timeout=25000)
            await _pause(2, 4)

            # One-way
            try:
                await page.evaluate("""
                () => {
                    const btns = document.querySelectorAll('[data-testid*="flightType"], [class*="flightType"]');
                    for (const b of btns) {
                        if (b.innerText.includes('One') || b.dataset.testid === 'flightType_OW' ||
                            b.innerText.includes('單') || b.innerText.includes('单')) {
                            b.click(); return;
                        }
                    }
                }
                """)
                await _pause(0.3, 0.6)
            except Exception:
                pass

            # Fill cities
            logger.info("  Filling origin: %s", origin)
            origin_text = {"LON": "London", "BJS": "Beijing", "PEK": "Beijing",
                           "SHA": "Shanghai", "PVG": "Shanghai", "HKG": "Hong Kong"}.get(origin, origin)
            dest_text = {"LON": "London", "BJS": "Beijing", "PEK": "Beijing",
                         "SHA": "Shanghai", "PVG": "Shanghai", "HKG": "Hong Kong"}.get(destination, destination)

            await _fill_city(page, "search_city_from0", origin_text)
            await _pause(0.5, 1.0)

            logger.info("  Filling destination: %s", destination)
            await _fill_city(page, "search_city_to0", dest_text)
            await _pause(0.5, 1.0)

            # Set date
            logger.info("  Setting date: %s", date)
            date_ok = await _set_date(page, date)
            logger.info("  Date set: %s", date_ok)

            await page.screenshot(path=f"/tmp/hk_trip_before_search_{date}.png")

            # Submit search
            logger.info("  Submitting search…")
            clicked = await page.evaluate("""
            () => {
                const sels = ['[data-testid="search_btn"]', '.nh_sf-searhBtn',
                               'button[class*="searchBtn"]', 'button[class*="search"]'];
                for (const sel of sels) {
                    const btn = document.querySelector(sel);
                    if (btn) { btn.click(); return sel; }
                }
                return null;
            }
            """)
            logger.info("  Search button: %s", clicked)

            # Wait for results — either API capture or DOM
            logger.info("  Waiting for results…")
            await _pause(12, 18)

            logger.info("  Final URL: %s", page.url)
            await page.screenshot(path=f"/tmp/hk_trip_results_{date}.png")

        except Exception as exc:
            logger.error("scrape_one error: %s", exc)
        finally:
            await page.close()
            await asyncio.sleep(random.uniform(3, 6))

        if captured:
            logger.info("Total flights captured: %d", len(captured))
            # Dedup (multiple API events can duplicate)
            seen: set[str] = set()
            unique = []
            for f in captured:
                uid = "|".join(f"{s['airline_code']}{s['flight_number']}" for s in f["segments"])
                if uid not in seen:
                    seen.add(uid)
                    unique.append(f)
            return sorted(unique, key=lambda f: f["price"])

        return []
