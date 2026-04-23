"""Browser fingerprint spoofing and human-like behaviour helpers for Playwright."""
from __future__ import annotations

import asyncio
import random
from typing import Optional

from playwright.async_api import Browser, BrowserContext, Page

# ── Fingerprint pools ─────────────────────────────────────────────────────────

USER_AGENTS: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 OPR/116.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

VIEWPORTS: list[dict] = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
    {"width": 1280, "height": 800},
    {"width": 1600, "height": 900},
]

# Stealth script: patch the most commonly checked fingerprint fields
_STEALTH_SCRIPT = """
() => {
    // Hide webdriver flag
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

    // Fake plugins (Chrome has them, headless doesn't by default)
    Object.defineProperty(navigator, 'plugins', {
        get: () => [1, 2, 3, 4, 5],
    });

    // Fake languages
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-HK', 'en-GB', 'en', 'zh-HK'],
    });

    // Chrome-specific: ensure window.chrome exists
    window.chrome = window.chrome || { runtime: {} };

    // Permissions API: make it look like a real browser
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : originalQuery(parameters)
    );

    // Hide automation-related properties
    delete navigator.__proto__.webdriver;
}
"""


# ── Context factory ───────────────────────────────────────────────────────────

async def create_stealth_context(
    browser: Browser,
    proxy: Optional[dict] = None,
    user_agent: Optional[str] = None,
) -> BrowserContext:
    """
    Create a Playwright BrowserContext with anti-detection settings.
    Matches hk.trip.com's expected locale/timezone.
    """
    ua = user_agent or random.choice(USER_AGENTS)
    vp = random.choice(VIEWPORTS)

    context_kwargs: dict = dict(
        user_agent=ua,
        viewport=vp,
        locale="en-HK",
        timezone_id="Asia/Hong_Kong",
        java_script_enabled=True,
        accept_downloads=False,
        extra_http_headers={
            "Accept-Language": "en-HK,en-GB;q=0.9,en;q=0.8,zh-HK;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "sec-ch-ua": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Upgrade-Insecure-Requests": "1",
        },
    )
    if proxy:
        context_kwargs["proxy"] = proxy

    context = await browser.new_context(**context_kwargs)
    await context.add_init_script(_STEALTH_SCRIPT)
    return context


# ── Human-like actions ────────────────────────────────────────────────────────

async def human_type(page: Page, selector: str, text: str) -> None:
    """Type text character-by-character with randomised inter-key delay."""
    await page.click(selector)
    await asyncio.sleep(random.uniform(0.2, 0.5))
    for char in text:
        await page.keyboard.type(char)
        await asyncio.sleep(random.uniform(0.04, 0.14))


async def human_pause(min_s: float = 1.5, max_s: float = 4.0) -> None:
    """Random pause to simulate reading / thinking."""
    await asyncio.sleep(random.uniform(min_s, max_s))


async def human_scroll(page: Page, direction: str = "down", steps: int = 3) -> None:
    """Scroll the page naturally."""
    delta = 300 if direction == "down" else -300
    for _ in range(steps):
        await page.mouse.wheel(0, delta + random.randint(-50, 50))
        await asyncio.sleep(random.uniform(0.3, 0.7))


async def move_mouse_naturally(page: Page, x: int, y: int) -> None:
    """Move mouse to target with slight randomisation (not a straight line)."""
    # Get current position (approximate centre if unknown)
    mid_x = x + random.randint(-60, 60)
    mid_y = y + random.randint(-40, 40)
    await page.mouse.move(mid_x, mid_y)
    await asyncio.sleep(random.uniform(0.05, 0.15))
    await page.mouse.move(x, y)


# ── Block detection ───────────────────────────────────────────────────────────

CAPTCHA_SIGNALS = [
    "captcha", "verify", "robot", "bot detection", "滑块", "验证码",
    "security check", "please verify", "access denied",
]

RATE_LIMIT_SIGNALS = [
    "429", "too many requests", "访问过于频繁", "rate limit",
    "请求频率", "temporarily blocked",
]


async def detect_block(page: Page) -> str | None:
    """
    Returns "captcha", "rate_limit", or None.
    Call this after page navigation to check if we've been blocked.
    """
    try:
        content = (await page.content()).lower()
        url = page.url.lower()

        for signal in CAPTCHA_SIGNALS:
            if signal in content or signal in url:
                return "captcha"

        for signal in RATE_LIMIT_SIGNALS:
            if signal in content:
                return "rate_limit"
    except Exception:
        pass
    return None
