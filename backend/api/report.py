"""Report generation API."""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ai.report_analyzer import analyze_report
from report.analytics import build_matrix, enrich_flights, summary_stats
from report.excel_builder import build_excel
from report.html_builder import build_html

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/report", tags=["report"])

REPORTS_DIR = Path(__file__).parent.parent / "data" / "reports"
INDEX_FILE  = REPORTS_DIR / "index.json"


# ── Models ────────────────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    title: str
    flights: list[dict]                # raw FlightResult dicts from search
    search_params: dict = {}
    date_ranges: list[dict] = []       # [{start, end}] for period-aggregated matrix
    user_query: str | None = None      # original chat question for AI analysis
    api_key: str | None = None         # BYOK Gemini key


class AnalyzeRequest(BaseModel):
    user_query: str | None = None
    api_key: str | None = None


class ReportMeta(BaseModel):
    report_id: str
    title: str
    created_at: str
    total_flights: int
    excel_file: str
    html_file: str
    stats: dict


# ── Index helpers ─────────────────────────────────────────────────────────────

def _inject_analysis(html_path: Path, analysis_html: str) -> None:
    """Insert AI analysis block into the HTML report after the KPI row."""
    html = html_path.read_text(encoding="utf-8")
    block = f"""
<!-- ── AI Analysis ─────────────────────────────────────────────────────────── -->
<div class="section" style="background:#fffbeb;border-bottom:1px solid #fde68a;">
  <div class="section-title" style="border-color:#f59e0b;color:#92400e;">🤖 AI 智能分析</div>
  <div style="color:#451a03;line-height:1.8;font-size:13px;">
    {analysis_html}
  </div>
</div>
"""
    # Insert after KPI row (before the first <div class="section">)
    marker = '<div class="section"'
    idx = html.find(marker)
    if idx != -1:
        html = html[:idx] + block + html[idx:]
    else:
        # Fallback: insert before </body>
        html = html.replace("</body>", block + "</body>")
    html_path.write_text(html, encoding="utf-8")


def _load_index() -> list[dict]:
    if not INDEX_FILE.exists():
        return []
    return json.loads(INDEX_FILE.read_text(encoding="utf-8"))


def _save_index(index: list[dict]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_FILE.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/generate", response_model=ReportMeta)
async def generate_report(req: GenerateRequest):
    if not req.flights:
        raise HTTPException(400, "No flight data provided")

    report_id = uuid.uuid4().hex[:8]
    report_dir = REPORTS_DIR / report_id
    report_dir.mkdir(parents=True, exist_ok=True)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Enrich + compute analytics
    enriched = enrich_flights(req.flights)
    matrix   = build_matrix(enriched)
    stats    = summary_stats(enriched)
    stats["generated_at"] = now_str

    excel_name = f"report_{report_id}.xlsx"
    html_name  = f"report_{report_id}.html"
    excel_path = report_dir / excel_name
    html_path  = report_dir / html_name

    # Save raw flights JSON (for AI analysis page)
    flights_path = report_dir / "flights.json"
    flights_path.write_text(
        json.dumps({"flights": req.flights, "date_ranges": req.date_ranges},
                   ensure_ascii=False),
        encoding="utf-8",
    )

    # Build files
    build_excel(excel_path, enriched, matrix, stats, req.title,
                date_ranges=req.date_ranges or None)
    build_html(html_path,  enriched, matrix, stats, req.title)

    # AI narrative analysis (optional, non-blocking failure)
    ai_analysis: str | None = None
    if req.api_key or os.environ.get("GEMINI_API_KEY"):
        try:
            ai_analysis = await analyze_report(
                stats=stats,
                title=req.title,
                user_query=req.user_query,
                api_key=req.api_key,
            )
            _inject_analysis(html_path, ai_analysis)
        except Exception as e:
            logger.warning("AI analysis failed (non-fatal): %s", e)

    meta: dict = {
        "report_id":    report_id,
        "title":        req.title,
        "created_at":   now_str,
        "total_flights": len(enriched),
        "excel_file":   excel_name,
        "html_file":    html_name,
        "has_flights":  True,
        "stats":        stats,
        "ai_analysis":  ai_analysis,
    }

    # Append to index
    index = _load_index()
    index.insert(0, meta)           # newest first
    _save_index(index)

    logger.info("Report %s generated (%d flights)", report_id, len(enriched))
    return meta


@router.get("/list")
async def list_reports():
    index = _load_index()
    # Dynamically check flights.json existence (backfills old reports)
    for r in index:
        if not r.get("has_flights"):
            r["has_flights"] = (REPORTS_DIR / r["report_id"] / "flights.json").exists()
    return index


@router.get("/{report_id}/excel")
async def download_excel(report_id: str):
    path = REPORTS_DIR / report_id / f"report_{report_id}.xlsx"
    if not path.exists():
        raise HTTPException(404, "Report not found")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=path.name,
    )


@router.get("/{report_id}/html")
async def get_html(report_id: str):
    path = REPORTS_DIR / report_id / f"report_{report_id}.html"
    if not path.exists():
        raise HTTPException(404, "Report not found")
    return FileResponse(path, media_type="text/html")


@router.post("/{report_id}/analyze")
async def analyze_report_endpoint(report_id: str, req: AnalyzeRequest):
    """(Re-)run AI analysis on an existing report and inject into its HTML."""
    report_dir = REPORTS_DIR / report_id
    meta_candidates = [r for r in _load_index() if r["report_id"] == report_id]
    if not meta_candidates:
        raise HTTPException(404, "Report not found")
    meta = meta_candidates[0]

    html_path = report_dir / meta["html_file"]
    if not html_path.exists():
        raise HTTPException(404, "Report HTML not found")

    try:
        analysis = await analyze_report(
            stats=meta["stats"],
            title=meta["title"],
            user_query=req.user_query,
            api_key=req.api_key,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"Gemini error: {e}")

    # Re-inject (rebuild HTML cleanly first to avoid double-inject)
    # Rebuild is simplest: just inject into the stored HTML
    _inject_analysis(html_path, analysis)

    # Update index
    index = _load_index()
    for r in index:
        if r["report_id"] == report_id:
            r["ai_analysis"] = analysis
    _save_index(index)

    return {"ok": True, "analysis": analysis}


@router.get("/{report_id}/flights")
async def get_flights(report_id: str):
    """Return raw flights JSON for analysis purposes."""
    path = REPORTS_DIR / report_id / "flights.json"
    if not path.exists():
        raise HTTPException(404, "Flights data not found for this report")
    return json.loads(path.read_text(encoding="utf-8"))


@router.delete("/{report_id}")
async def delete_report(report_id: str):
    report_dir = REPORTS_DIR / report_id
    if not report_dir.exists():
        raise HTTPException(404, "Report not found")

    import shutil
    shutil.rmtree(report_dir)

    index = [r for r in _load_index() if r["report_id"] != report_id]
    _save_index(index)
    return {"ok": True}
