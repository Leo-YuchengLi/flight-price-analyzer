"""
One-time discovery script: load Trip.com, submit a flight search, and
capture all API requests so we know the real endpoint + payload structure.

Run with:  cd backend && python -m scraper.discover_api
"""
import asyncio
import json
import logging
import sys
from pathlib import Path

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

OUT_FILE = Path(__file__).parent / "api_discovery.json"


# ── Helpers ───────────────────────────────────────────────────────────────────

async def dismiss_dropdowns(page) -> None:
    """Close any open autocomplete / POI dropdowns."""
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(300)
    # Also click neutral space (top-left corner of page)
    await page.evaluate("""
    () => {
        const el = document.querySelector('[class*="nh_sf-title"], h1, .trip-header, header');
        if (el) el.click();
    }
    """)
    await page.wait_for_timeout(300)


async def set_city(page, test_id: str, city_text: str) -> bool:
    """Fill a city field using Trip.com's autocomplete."""
    try:
        # Use JS click to avoid overlay issues
        await page.evaluate(f"""
        () => {{
            const el = document.querySelector('[data-testid="{test_id}"]');
            if (el) el.click();
        }}
        """)
        await page.wait_for_timeout(400)

        locator = page.locator(f'[data-testid="{test_id}"]').first
        await locator.fill("")
        await page.wait_for_timeout(200)

        for char in city_text:
            await page.keyboard.type(char)
            await asyncio.sleep(0.07)

        await page.wait_for_timeout(1800)  # wait for autocomplete

        # Try clicking first autocomplete item
        dropdown_sels = [
            ".m-flight-poi-list li",
            ".m-flight-poi-list .item",
            "[class*='poi-list'] li",
            "[class*='poi-list'] [class*='item']",
            "[class*='suggest'] li",
        ]
        for sel in dropdown_sels:
            count = await page.locator(sel).count()
            if count > 0:
                await page.locator(sel).first.click()
                logger.info("  '%s' selected via '%s' (%d items)", city_text, sel, count)
                await page.wait_for_timeout(600)
                # Force-dismiss the dropdown
                await dismiss_dropdowns(page)
                return True

        # No dropdown found — try Enter
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(400)
        await dismiss_dropdowns(page)
        return True

    except Exception as exc:
        logger.error("  set_city(%s) failed: %s", test_id, exc)
        return False


async def open_calendar_via_js(page) -> bool:
    """
    Click the date picker trigger using JavaScript (bypasses POI overlay).
    Returns True if the calendar appears to have opened.
    """
    result = await page.evaluate("""
    () => {
        // The hidden input; we need to click its VISIBLE parent wrapper
        const hiddenInput = document.querySelector('[data-testid="search_date_depart0"]');
        if (!hiddenInput) return { ok: false, reason: 'no date input found' };

        // Walk up the DOM to find a container with "date" in its class
        let el = hiddenInput.parentElement;
        for (let i = 0; i < 15; i++) {
            if (!el || el === document.body) break;
            const cls = (el.className || '').toLowerCase();
            if (cls.includes('date') || cls.includes('calendar') || cls.includes('depart')) {
                el.click();
                return { ok: true, clicked: el.className, i };
            }
            el = el.parentElement;
        }

        // Fallback: just click the hidden input via JS
        hiddenInput.click();
        return { ok: true, clicked: 'hidden_input_fallback' };
    }
    """)
    logger.info("  calendar open result: %s", result)
    await page.wait_for_timeout(800)

    # Verify a calendar opened
    cal_visible = await page.evaluate("""
    () => {
        const cal = document.querySelector(
            '[class*="calendar"], [class*="Calendar"], [class*="datepicker"], [class*="date-picker"]'
        );
        return !!cal;
    }
    """)
    return cal_visible


async def navigate_calendar_to_month(page, target_year: int, target_month: int) -> bool:
    """Navigate the open calendar to the target month/year."""
    import calendar as cal_mod

    for attempt in range(28):  # up to 28 months forward
        # Read the currently visible months from all calendar headers
        headers = await page.evaluate("""
        () => {
            const sels = [
                '[class*="calendar"] [class*="month"]',
                '[class*="calendar"] [class*="title"]',
                '[class*="calendar"] [class*="header"]',
                '[class*="picker"] [class*="month"]',
            ];
            const texts = new Set();
            for (const s of sels) {
                document.querySelectorAll(s).forEach(el => {
                    const t = el.innerText?.trim();
                    if (t && t.length > 2 && t.length < 30) texts.add(t);
                });
            }
            return [...texts];
        }
        """)
        logger.info("  [%d] Calendar headers: %s", attempt, headers)

        # Check if target month is visible
        month_name = cal_mod.month_name[target_month]   # e.g. "June"
        short_month = cal_mod.month_abbr[target_month]   # e.g. "Jun"
        target_found = any(
            (month_name in h or short_month in h) and str(target_year) in h
            for h in headers
        )
        if target_found:
            logger.info("  Found target month: %s %d", month_name, target_year)
            return True

        # Click next-month button via JS
        clicked = await page.evaluate("""
        () => {
            // All buttons inside calendar-like containers
            const candidates = Array.from(document.querySelectorAll(
                '[class*="calendar"] button, [class*="Calendar"] button, ' +
                '[class*="picker"] button, [class*="datepicker"] button'
            )).filter(b => !b.disabled);

            if (candidates.length === 0) return { ok: false, reason: 'no buttons' };

            // Sort by bounding rect right-edge descending (rightmost = "next")
            const withRect = candidates.map(b => ({ b, r: b.getBoundingClientRect() }))
                .filter(x => x.r.width > 0);
            withRect.sort((a, b) => b.r.right - a.r.right);

            // The rightmost non-disabled button
            const next = withRect[0];
            if (next) {
                next.b.click();
                return { ok: true, text: next.b.innerText, class: next.b.className };
            }
            return { ok: false, reason: 'no valid next button' };
        }
        """)
        logger.info("  next-month click: %s", clicked)

        if not clicked.get("ok"):
            logger.warning("  Could not find next-month button on attempt %d", attempt)
            return False

        await page.wait_for_timeout(500)

    logger.warning("  Reached max 28 attempts without finding target month")
    return False


async def click_day_in_calendar(page, day: int) -> bool:
    """Click a specific day number in the open calendar."""
    target_day = str(day)

    result = await page.evaluate(f"""
    () => {{
        const day = '{target_day}';

        // Try td cells, then day-number divs/spans
        const sels = [
            '[class*="calendar"] td',
            '[class*="calendar"] [class*="day"]',
            '[class*="Calendar"] td',
            '[class*="picker"] td',
            '[class*="calendar"] button',
        ];

        for (const sel of sels) {{
            const cells = Array.from(document.querySelectorAll(sel));
            for (const cell of cells) {{
                const text = cell.innerText?.trim();
                if (text === day) {{
                    const cls = (cell.className || '').toLowerCase();
                    // Skip disabled / grayed days
                    if (cls.includes('disable') || cls.includes('gray') || cell.disabled) continue;
                    cell.click();
                    return {{ ok: true, sel, cls: cell.className }};
                }}
            }}
        }}
        return {{ ok: false, day }};
    }}
    """)
    logger.info("  day click: %s", result)
    await page.wait_for_timeout(400)
    return result.get("ok", False)


async def set_date_via_calendar(page, date_str: str) -> bool:
    """
    Full calendar flow: open → navigate → click day.
    date_str: YYYY-MM-DD
    """
    from datetime import date as dt
    target = dt.fromisoformat(date_str)

    # Ensure no overlay is blocking
    await dismiss_dropdowns(page)
    await page.wait_for_timeout(500)

    # Open calendar
    if not await open_calendar_via_js(page):
        logger.warning("  Calendar did not appear to open")
        # Try anyway — it might still be there

    # Navigate to target month
    if not await navigate_calendar_to_month(page, target.year, target.month):
        return False

    # Click the day
    return await click_day_in_calendar(page, target.day)


# ── Main discovery flow ───────────────────────────────────────────────────────

async def discover(origin: str = "LON", dest: str = "BJS", date: str = "2026-06-15"):
    captured_requests = []
    captured_responses = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel="chrome",
            headless=False,
            args=["--window-size=1400,900"],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1400, "height": 900},
            locale="en-HK",
            timezone_id="Asia/Hong_Kong",
        )
        page = await context.new_page()

        async def on_request(req):
            url = req.url
            method = req.method
            if method == "POST" or "flight" in url.lower():
                entry = {
                    "url": url,
                    "method": method,
                    "post_data": req.post_data,
                }
                captured_requests.append(entry)
                if "flight" in url.lower() and method == "POST":
                    logger.info("FLIGHT REQUEST: %s %s", method, url[:120])

        async def on_response(resp):
            url = resp.url
            ct = resp.headers.get("content-type", "")
            if "json" in ct and ("flight" in url.lower() or "list" in url.lower() or "search" in url.lower()):
                try:
                    body = await resp.json()
                    entry = {"url": url, "status": resp.status, "body_keys": list(body.keys()) if isinstance(body, dict) else str(type(body))}
                    captured_responses.append(entry)
                    logger.info("FLIGHT RESPONSE: %d %s keys=%s", resp.status, url[:100], entry["body_keys"])
                    # Save full body for interesting responses
                    if isinstance(body, dict) and any(k in body for k in ["flightList", "flightItineraryList", "data", "result"]):
                        captured_responses[-1]["body"] = body
                except Exception:
                    pass

        page.on("request", on_request)
        page.on("response", on_response)

        # ── Load Trip.com ──────────────────────────────────────────────────────
        logger.info("Loading www.trip.com/flights/...")
        await page.goto("https://www.trip.com/flights/", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        # ── Select one-way ─────────────────────────────────────────────────────
        try:
            await page.evaluate("""
            () => {
                const btns = document.querySelectorAll('[data-testid*="flightType"]');
                for (const btn of btns) {
                    if (btn.innerText.includes('One') || btn.dataset.testid === 'flightType_OW') {
                        btn.click(); return;
                    }
                }
            }
            """)
            logger.info("Selected one-way")
            await page.wait_for_timeout(500)
        except Exception as e:
            logger.warning("OW select: %s", e)

        # ── Fill cities ────────────────────────────────────────────────────────
        logger.info("Filling origin: London")
        await set_city(page, "search_city_from0", "London")
        await page.wait_for_timeout(500)

        logger.info("Filling destination: Beijing")
        await set_city(page, "search_city_to0", "Beijing")
        await page.wait_for_timeout(800)

        # Inspect form state
        form_state = await page.evaluate("""
        () => {
            const ids = ['search_city_from0', 'search_city_to0', 'search_date_depart0'];
            const out = {};
            for (const id of ids) {
                const el = document.querySelector(`[data-testid="${id}"]`);
                if (el) out[id] = { value: el.value || '', innerText: el.innerText?.slice(0, 30), dataDate: el.dataset?.date };
            }
            return out;
        }
        """)
        logger.info("Form state after cities: %s", json.dumps(form_state, ensure_ascii=False))

        await page.screenshot(path="/tmp/trip_cities_filled.png")

        # ── Set date ───────────────────────────────────────────────────────────
        logger.info("Setting date: %s", date)
        date_ok = await set_date_via_calendar(page, date)
        logger.info("Date set: %s", date_ok)

        # Check form state again
        form_state2 = await page.evaluate("""
        () => {
            const el = document.querySelector('[data-testid="search_date_depart0"]');
            return el ? { value: el.value, dataDate: el.dataset?.date } : null;
        }
        """)
        logger.info("Date field after calendar: %s", form_state2)
        await page.screenshot(path="/tmp/trip_date_set.png")

        # ── Submit search ──────────────────────────────────────────────────────
        logger.info("Clicking search button...")
        try:
            clicked = await page.evaluate("""
            () => {
                const sels = [
                    '[data-testid="search_btn"]',
                    '.nh_sf-searhBtn',
                    'button[class*="searchBtn"]',
                    'button[class*="search-btn"]',
                ];
                for (const sel of sels) {
                    const btn = document.querySelector(sel);
                    if (btn) { btn.click(); return sel; }
                }
                return null;
            }
            """)
            logger.info("Search button clicked via: %s", clicked)
        except Exception as e:
            logger.error("Search click: %s", e)

        logger.info("Waiting for results (15s)...")
        await page.wait_for_timeout(15000)

        logger.info("Final URL: %s", page.url)
        await page.screenshot(path="/tmp/trip_results.png")

        # ── Dump captured data ─────────────────────────────────────────────────
        flight_reqs = [r for r in captured_requests if "flight" in r["url"].lower() and r["method"] == "POST"]
        logger.info("Flight POST requests captured: %d", len(flight_reqs))
        for r in flight_reqs:
            logger.info("  URL: %s", r["url"])
            if r["post_data"]:
                logger.info("  Payload: %s", r["post_data"][:300])

        logger.info("Interesting responses: %d", len([r for r in captured_responses if "body" in r]))

        results = {
            "origin": origin,
            "dest": dest,
            "date": date,
            "final_url": page.url,
            "flight_post_requests": flight_reqs[:10],
            "interesting_responses": [
                {k: v for k, v in r.items() if k != "body"} for r in captured_responses
            ],
        }
        # Save full bodies separately
        for i, r in enumerate(captured_responses):
            if "body" in r:
                body_file = Path(__file__).parent / f"api_response_{i}.json"
                body_file.write_text(json.dumps(r["body"], indent=2, ensure_ascii=False))
                logger.info("Saved response body to: %s", body_file)

        OUT_FILE.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        logger.info("Discovery results saved to: %s", OUT_FILE)

        await browser.close()

    return results


if __name__ == "__main__":
    origin = sys.argv[1] if len(sys.argv) > 1 else "LON"
    dest = sys.argv[2] if len(sys.argv) > 2 else "BJS"
    date = sys.argv[3] if len(sys.argv) > 3 else "2026-06-15"
    asyncio.run(discover(origin, dest, date))
