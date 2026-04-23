"""
诊断脚本：检查反爬虫指纹 + 测试各数据源可访问性
运行: cd backend && python -m scraper.diagnose
"""
import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

try:
    from playwright_stealth import stealth_async
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SHOTS_DIR = Path("/tmp/debug_screenshots")
SHOTS_DIR.mkdir(exist_ok=True)


async def shot(page, name: str) -> None:
    ts = datetime.now().strftime("%H%M%S")
    path = SHOTS_DIR / f"{ts}_{name}.png"
    await page.screenshot(path=str(path), full_page=False)
    logger.info("  📸 Screenshot: %s (URL=%s)", path.name, page.url[:80])


async def check_fingerprint(page) -> dict:
    """Check what the bot-detection sees."""
    return await page.evaluate("""
    () => ({
        webdriver:       navigator.webdriver,
        plugins:         navigator.plugins.length,
        languages:       navigator.languages,
        userAgent:       navigator.userAgent.slice(0, 60),
        chromeRuntime:   !!(window.chrome && window.chrome.runtime),
        outerWidth:      window.outerWidth,
        outerHeight:     window.outerHeight,
        innerWidth:      window.innerWidth,
        innerHeight:     window.innerHeight,
        deviceMemory:    navigator.deviceMemory,
        hardwareConcurrency: navigator.hardwareConcurrency,
    })
    """)


async def test_source(browser, name: str, url: str,
                      wait_sel: str = None, timeout: int = 20000) -> dict:
    """Generic source test: load URL, screenshot, check for bot blocks."""
    logger.info("\n── Testing %s ──────────────────────────────", name)
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        viewport={"width": 1400, "height": 900},
        locale="en-HK",
        timezone_id="Asia/Hong_Kong",
        extra_http_headers={"Accept-Language": "en-HK,en-GB;q=0.9,en;q=0.8"},
    )
    page = await context.new_page()
    if HAS_STEALTH:
        await stealth_async(page)

    result = {"name": name, "url": url, "status": "unknown", "final_url": "", "blocked": False}
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        await asyncio.sleep(2)
        result["final_url"] = page.url
        result["title"] = await page.title()

        fp = await check_fingerprint(page)
        result["fingerprint"] = fp
        logger.info("  Fingerprint: webdriver=%s plugins=%d chrome=%s",
                    fp["webdriver"], fp["plugins"], fp["chromeRuntime"])

        # Check for bot/captcha blocks
        content = (await page.content()).lower()
        blocked_signals = ["captcha", "verify", "robot", "access denied", "bot detected", "滑块", "验证码"]
        result["blocked"] = any(s in content for s in blocked_signals)
        result["status"] = "blocked" if result["blocked"] else "accessible"

        if wait_sel:
            try:
                await page.wait_for_selector(wait_sel, timeout=5000)
                result["target_selector_found"] = True
            except Exception:
                result["target_selector_found"] = False

        await shot(page, name.replace(" ", "_"))
        logger.info("  Status: %s | Final URL: %s | Blocked: %s",
                    result["status"], result["final_url"][:70], result["blocked"])

    except Exception as exc:
        result["status"] = "error"
        result["error"] = str(exc)[:200]
        logger.error("  Error: %s", exc)
        try:
            await shot(page, f"{name.replace(' ', '_')}_error")
        except Exception:
            pass
    finally:
        await context.close()

    return result


async def test_bot_sannysoft(browser) -> dict:
    """Check bot.sannysoft.com — the classic fingerprint test."""
    logger.info("\n── Bot Detection Test (bot.sannysoft.com) ────────────────")
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        viewport={"width": 1400, "height": 900},
        locale="en-HK",
    )
    page = await context.new_page()
    if HAS_STEALTH:
        await stealth_async(page)

    result = {}
    try:
        await page.goto("https://bot.sannysoft.com/", wait_until="networkidle", timeout=20000)
        await asyncio.sleep(3)
        await shot(page, "bot_sannysoft")

        # Extract test results from the table
        rows = await page.evaluate("""
        () => {
            const rows = Array.from(document.querySelectorAll('table tr'));
            return rows.map(r => ({
                test: r.cells[0]?.innerText?.trim(),
                result: r.cells[1]?.innerText?.trim(),
                pass: r.cells[1]?.style?.background !== 'red' &&
                      !r.cells[1]?.className?.includes('failed'),
            })).filter(r => r.test);
        }
        """)
        result["rows"] = rows[:20]
        failed = [r for r in rows if r.get("result") == "FAILED" or "bot" in (r.get("result") or "").lower()]
        result["failed_count"] = len(failed)
        result["failed_tests"] = [r["test"] for r in failed]
        logger.info("  Failed checks: %d — %s", len(failed), result["failed_tests"])
    except Exception as exc:
        result["error"] = str(exc)
    finally:
        await context.close()
    return result


async def test_hk_trip_search(browser, origin="LON", dest="BJS", date="2026-06-15") -> dict:
    """Full hk.trip.com form interaction with stealth."""
    logger.info("\n── hk.trip.com Full Form Test ────────────────────────────")
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        viewport={"width": 1400, "height": 900},
        locale="en-HK",
        timezone_id="Asia/Hong_Kong",
    )
    page = await context.new_page()
    if HAS_STEALTH:
        await stealth_async(page)
        logger.info("  playwright-stealth applied")

    captured_flights = []
    captured_api_urls = []

    async def on_response(resp):
        ct = resp.headers.get("content-type", "")
        if "json" in ct:
            url = resp.url
            if any(k in url for k in ["FlightList", "itinerary", "flight", "FlightMiddle"]):
                try:
                    body = await resp.json()
                    if isinstance(body, dict):
                        itin = body.get("itineraryList") or []
                        if itin:
                            captured_flights.extend(itin)
                            captured_api_urls.append(url)
                            logger.info("  🎯 Captured %d itineraries from %s", len(itin), url[:80])
                except Exception:
                    pass

    page.on("response", on_response)

    result = {"flights_captured": 0, "api_url": "", "status": "unknown"}
    try:
        # Step 1: Load hk.trip.com homepage
        logger.info("  Loading hk.trip.com...")
        await page.goto("https://hk.trip.com/", wait_until="domcontentloaded", timeout=25000)
        await asyncio.sleep(random_pause(2, 4))
        await shot(page, "hktrip_01_homepage")
        logger.info("  Loaded: %s", page.url)

        fp = await check_fingerprint(page)
        logger.info("  Fingerprint: webdriver=%s plugins=%d chrome=%s",
                    fp["webdriver"], fp["plugins"], fp["chromeRuntime"])

        # Step 2: Navigate to flights section
        logger.info("  Looking for flights link...")
        flight_link_sels = [
            'a[href*="flight"]', 'a[href*="flights"]',
            '[class*="flight"]', 'a:has-text("Flights")',
            'a:has-text("Flight")', '[data-tabid="flight"]',
        ]
        for sel in flight_link_sels:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    await el.click()
                    logger.info("  Clicked flights link: %s", sel)
                    await asyncio.sleep(random_pause(1, 2))
                    break
            except Exception:
                pass

        await shot(page, "hktrip_02_after_flights_click")

        # Step 3: Go to flights search page directly if not already there
        if "flights" not in page.url:
            await page.goto("https://hk.trip.com/flights/", wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(random_pause(2, 3))
            await shot(page, "hktrip_03_flights_page")
            logger.info("  Navigated to flights page: %s", page.url)

        # Step 4: Inspect the DOM structure
        form_info = await page.evaluate("""
        () => {
            const result = {};
            // Find all inputs
            result.inputs = Array.from(document.querySelectorAll('input')).slice(0, 20).map(i => ({
                type: i.type, placeholder: i.placeholder, testid: i.dataset.testid,
                name: i.name, id: i.id, value: i.value
            }));
            // Find search button
            result.searchBtns = Array.from(document.querySelectorAll('button')).slice(0, 10).map(b => ({
                text: b.innerText.trim().slice(0, 30),
                testid: b.dataset.testid,
                class: b.className.slice(0, 40)
            }));
            // Find date elements
            result.dateEls = Array.from(document.querySelectorAll('[data-testid*="date"], [class*="date"]')).slice(0, 5).map(e => ({
                tag: e.tagName, testid: e.dataset.testid, class: e.className.slice(0, 50),
                text: e.innerText.trim().slice(0, 30)
            }));
            return result;
        }
        """)
        logger.info("  Form inputs found: %d | Search buttons: %d",
                    len(form_info.get("inputs", [])), len(form_info.get("searchBtns", [])))
        logger.info("  Date elements: %s", form_info.get("dateEls", []))

        result["form_info"] = form_info
        result["status"] = "form_loaded"

    except Exception as exc:
        result["status"] = "error"
        result["error"] = str(exc)[:200]
        logger.error("  Error: %s", exc)
        try:
            await shot(page, "hktrip_error")
        except Exception:
            pass
    finally:
        result["flights_captured"] = len(captured_flights)
        result["api_urls"] = captured_api_urls
        await context.close()

    return result


def random_pause(mn=1.0, mx=3.0) -> float:
    import random
    return random.uniform(mn, mx)


async def main():
    logger.info("=" * 60)
    logger.info("Flight Scraper Diagnostic")
    logger.info("Screenshots → %s", SHOTS_DIR)
    logger.info("=" * 60)

    results = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel="chrome",
            headless=False,   # visible for diagnosis
            args=["--window-size=1400,900", "--no-sandbox"],
        )

        # 1. Bot detection fingerprint test
        results["bot_sannysoft"] = await test_bot_sannysoft(browser)

        # 2. Test each source
        sources = [
            ("hk.trip.com flights", "https://hk.trip.com/flights/", None),
            ("www.trip.com flights", "https://www.trip.com/flights/", None),
            ("Skyscanner LON-BJS", "https://www.skyscanner.net/transport/flights/lon/bjsp/260615/", None),
        ]
        results["sources"] = []
        for name, url, sel in sources:
            r = await test_source(browser, name, url, sel)
            results["sources"].append(r)
            await asyncio.sleep(2)

        # 3. Full hk.trip.com form test
        results["hk_form_test"] = await test_hk_trip_search(browser)

        await browser.close()

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("DIAGNOSTIC SUMMARY")
    print("=" * 60)

    bot_result = results.get("bot_sannysoft", {})
    print(f"\n🔬 Bot Detection (bot.sannysoft.com):")
    print(f"   Failed checks: {bot_result.get('failed_count', '?')}")
    if bot_result.get('failed_tests'):
        print(f"   Failed: {bot_result['failed_tests']}")

    print("\n🌐 Source Accessibility:")
    for s in results.get("sources", []):
        icon = "✅" if not s.get("blocked") and s.get("status") == "accessible" else "❌"
        print(f"   {icon} {s['name']}: {s['status']} → {s.get('final_url', '')[:60]}")

    hk = results.get("hk_form_test", {})
    print(f"\n🔍 hk.trip.com Form Test:")
    print(f"   Status: {hk.get('status')}")
    print(f"   Flights captured: {hk.get('flights_captured', 0)}")
    if hk.get("api_urls"):
        print(f"   API URLs hit: {hk['api_urls']}")

    print(f"\n📸 Screenshots saved to: {SHOTS_DIR}")
    print("\n💡 Free Alternative Data Sources:")
    print("   1. Amadeus for Developers API (free sandbox + 100 prod calls/month)")
    print("      URL: https://developers.amadeus.com/self-service/category/flights")
    print("      - Flight Offers Search: origin/dest/date → prices + schedules")
    print("      - No scraping needed, official JSON API")
    print()
    print("   2. Google Flights via fast-flights library (free, unofficial)")
    print("      pip install fast-flights")
    print("      Uses Google's internal ITA Matrix API")
    print()
    print("   3. Kiwi.com / Tequila API (limited free tier)")
    print("      https://tequila.kiwi.com/")
    print()
    print("   4. hk.trip.com DOM scraping (what we're testing here)")
    print("      Lower anti-bot than www.trip.com")

    # Save full results
    out = Path(__file__).parent / "diagnostic_results.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str))
    print(f"\n📄 Full results: {out}")


if __name__ == "__main__":
    asyncio.run(main())
