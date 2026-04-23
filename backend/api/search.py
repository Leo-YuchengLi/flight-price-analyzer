"""Search API — SSE streaming endpoint for classic form search."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid as uuid_module
from datetime import date as dt_date
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from models.schemas import ClassicSearchRequest
from scraper.cache import SearchCache
from scraper.cities import all_cities, resolve_iata
from scraper.trip_scraper import TripScraper

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/search", tags=["search"])

# Single shared scraper instance (browser stays open between requests)
_scraper: TripScraper | None = None
_cache: SearchCache | None = None
# Lock to prevent two parallel requests from both calling scraper.start()
# simultaneously (race condition: both see _browser is None and double-init)
_scraper_init_lock = asyncio.Lock()

DATA_DIR = Path(__file__).parent.parent / "data"
CHECKPOINTS_DIR = DATA_DIR / "checkpoints"


# ── Checkpoint models ─────────────────────────────────────────────────────────

class CheckpointRequest(BaseModel):
    checkpoint_id: Optional[str] = None
    flights: list[dict]
    date_ranges: list[dict] = []
    title: str = ""


def get_scraper(headless: bool = True) -> TripScraper:
    global _scraper
    if _scraper is None:
        _scraper = TripScraper(headless=headless)
    return _scraper


def get_cache() -> SearchCache:
    global _cache
    if _cache is None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _cache = SearchCache(DATA_DIR / "cache.db")
    return _cache


def _sse(payload: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _apply_weekday_filter(dates: list[str], weekday_filter: list[int]) -> list[str]:
    """Keep only dates whose weekday is in the filter. Empty filter = keep all."""
    if not weekday_filter:
        return dates
    days = set(weekday_filter)
    return [d for d in dates if dt_date.fromisoformat(d).weekday() in days]


async def _ensure_scraper(dry_run: bool, show_browser: bool) -> TripScraper:
    """Get or recreate scraper, restarting if headless mode needs to change."""
    global _scraper
    want_headless = not show_browser
    if not dry_run:
        if _scraper is not None and _scraper.headless != want_headless:
            logger.info("Headless mode changing to %s — restarting browser", want_headless)
            await _scraper.stop()
            _scraper = None
    if _scraper is None:
        _scraper = TripScraper(headless=want_headless)
    return _scraper


async def _run_search(req: ClassicSearchRequest):
    """Async generator yielding SSE strings. Always re-scrapes — no cache."""
    scraper = await _ensure_scraper(req.dry_run, req.show_browser)

    # Resolve IATA codes
    origin = resolve_iata(req.origin) or req.origin.upper()
    destination = resolve_iata(req.destination) or req.destination.upper()

    # Apply weekday filter to outbound dates
    dates = _apply_weekday_filter(req.dates, req.weekday_filter)
    if not dates:
        yield _sse({"type": "error", "message": "所选日期过滤后为空，请检查星期筛选设置"})
        return

    # For round-trip, apply same filter to return dates
    return_dates = _apply_weekday_filter(req.return_dates, req.weekday_filter) \
        if req.trip_type == "round_trip" else []

    # Build full job list: outbound legs + (for round-trip) return legs
    jobs = [("out", origin, destination, d) for d in dates]
    if req.trip_type == "round_trip" and return_dates:
        jobs += [("ret", destination, origin, d) for d in return_dates]

    total = len(jobs)
    all_flights = []

    yield _sse({"type": "progress",
                "message": f"准备搜索 {origin} → {destination}，共 {len(dates)} 个出发日"
                           + (f" + {len(return_dates)} 个返回日" if return_dates else ""),
                "current": 0, "total": total})

    # Start browser — protected by a lock so two parallel requests don't both
    # see _browser=None and call start() simultaneously (double-init corrupts state)
    if not req.dry_run:
        if scraper._browser is None:
            yield _sse({"type": "progress", "message": "启动浏览器…", "current": 0, "total": total})
        async with _scraper_init_lock:
            if scraper._browser is None:
                await scraper.start()
            else:
                scraper._route_count += 1

    for i, (leg, org, dst, date) in enumerate(jobs, 1):
        leg_label = "去程" if leg == "out" else "返程"
        yield _sse({"type": "progress",
                    "message": f"[{i}/{total}] {leg_label} {org}→{dst} {date}…",
                    "current": i, "total": total})

        try:
            flights = await scraper.scrape_one(
                origin=org,
                destination=dst,
                date=date,
                cabin=req.cabin,
                currency=req.currency,
                trip_type="one_way",   # each leg is always scraped as one-way
                dry_run=req.dry_run,
            )

            # Tag flights with leg info for round-trip
            if req.trip_type == "round_trip":
                for f in flights:
                    f["leg"] = leg

            yield _sse({"type": "result", "date": date, "leg": leg, "flights": flights, "cached": False})
            all_flights.extend(flights)

        except Exception as exc:
            logger.error("Search error for %s: %s", date, exc)
            yield _sse({"type": "error", "message": str(exc), "date": date})

    yield _sse({"type": "done", "total_flights": len(all_flights), "total_dates": total})


@router.post("/classic")
async def search_classic(req: ClassicSearchRequest):
    """
    Stream flight search results as Server-Sent Events.
    Client reads via fetch() + ReadableStream.
    """
    return StreamingResponse(
        _run_search(req),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/checkpoint")
async def save_checkpoint(req: CheckpointRequest):
    """Incrementally persist flight data during a long batch search (crash safety)."""
    cp_id = req.checkpoint_id or uuid_module.uuid4().hex[:8]
    CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)
    path = CHECKPOINTS_DIR / f"{cp_id}.json"

    stored: dict = {"flights": [], "date_ranges": [], "title": req.title}
    if path.exists():
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass

    stored["flights"].extend(req.flights)
    if req.date_ranges:
        stored["date_ranges"] = req.date_ranges
    if req.title:
        stored["title"] = req.title

    path.write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")
    logger.info("Checkpoint %s: %d total flights saved", cp_id, len(stored["flights"]))
    return {"checkpoint_id": cp_id, "total_saved": len(stored["flights"])}


@router.get("/checkpoint/{checkpoint_id}")
async def get_checkpoint(checkpoint_id: str):
    """Retrieve all flights saved in a checkpoint (for resume / report generation)."""
    path = CHECKPOINTS_DIR / f"{checkpoint_id}.json"
    if not path.exists():
        raise HTTPException(404, "Checkpoint not found")
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/cities")
async def get_cities():
    """Return all known cities for autocomplete."""
    return all_cities()


@router.get("/status")
async def get_status():
    cache = get_cache()
    return {
        "scraper_ready": _scraper is not None and _scraper._browser is not None,
        "cache": cache.stats(),
    }
