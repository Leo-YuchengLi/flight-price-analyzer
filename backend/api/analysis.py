"""AI Analysis Report — API endpoints."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from ai.analysis_generator import chat_stream, generate_outline, generate_report_stream

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analysis", tags=["analysis"])

ANALYSES_DIR = Path(__file__).parent.parent / "data" / "analyses"
INDEX_FILE   = ANALYSES_DIR / "index.json"


# ── Models ────────────────────────────────────────────────────────────────────

class OutlineRequest(BaseModel):
    title: str
    flights: list[dict]
    date_ranges: list[dict] = []
    api_key: str | None = None


class GenerateRequest(BaseModel):
    title: str
    flights: list[dict]
    outline: str
    date_ranges: list[dict] = []
    api_key: str | None = None


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []
    api_key: str | None = None


# ── Index helpers ─────────────────────────────────────────────────────────────

def _load_index() -> list[dict]:
    if not INDEX_FILE.exists():
        return []
    try:
        return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_index(entries: list[dict]) -> None:
    ANALYSES_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_FILE.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/outline")
async def get_outline(req: OutlineRequest):
    """Generate a report outline from raw flight data."""
    if not req.flights:
        raise HTTPException(400, "No flight data provided")
    try:
        outline = await generate_outline(
            flights=req.flights,
            title=req.title,
            date_ranges=req.date_ranges or None,
            api_key=req.api_key,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error("Outline generation failed: %s", e)
        raise HTTPException(502, f"AI error: {e}")
    return {"outline": outline}


@router.post("/generate")
async def generate_analysis(req: GenerateRequest):
    """Stream the full analysis report (SSE). Saves to disk when complete."""
    if not req.flights:
        raise HTTPException(400, "No flight data provided")

    analysis_id = uuid.uuid4().hex[:8]
    analysis_dir = ANALYSES_DIR / analysis_id
    analysis_dir.mkdir(parents=True, exist_ok=True)

    now_str   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html_file = f"analysis_{analysis_id}.html"
    html_path = analysis_dir / html_file

    # Save outline
    (analysis_dir / "outline.txt").write_text(req.outline, encoding="utf-8")

    async def event_stream():
        full_html: list[str] = []
        try:
            async for chunk in generate_report_stream(
                flights=req.flights,
                title=req.title,
                outline=req.outline,
                date_ranges=req.date_ranges or None,
                api_key=req.api_key,
            ):
                full_html.append(chunk)
                yield f"data: {json.dumps({'type': 'chunk', 'text': chunk})}\n\n"
        except Exception as e:
            logger.error("Report generation error: %s", e)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            return

        # Persist complete HTML
        complete = "".join(full_html)
        html_path.write_text(complete, encoding="utf-8")

        meta: dict = {
            "analysis_id": analysis_id,
            "title":       req.title,
            "created_at":  now_str,
            "html_file":   html_file,
            "outline":     req.outline,
        }
        index = _load_index()
        index.insert(0, meta)
        _save_index(index)

        logger.info("Analysis %s saved (%d chars)", analysis_id, len(complete))
        yield f"data: {json.dumps({'type': 'done', 'analysis_id': analysis_id})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/list")
async def list_analyses():
    return _load_index()


@router.get("/{analysis_id}")
async def get_analysis(analysis_id: str):
    index = _load_index()
    entry = next((r for r in index if r["analysis_id"] == analysis_id), None)
    if not entry:
        raise HTTPException(404, "Analysis not found")
    html_path = ANALYSES_DIR / analysis_id / entry["html_file"]
    html_content = html_path.read_text(encoding="utf-8") if html_path.exists() else ""
    return {**entry, "html_content": html_content}


@router.get("/{analysis_id}/html")
async def download_analysis_html(analysis_id: str):
    """Serve the full HTML report. Wraps legacy fragment reports in a full document."""
    index = _load_index()
    entry = next((r for r in index if r["analysis_id"] == analysis_id), None)
    if not entry:
        raise HTTPException(404, "Analysis not found")
    html_path = ANALYSES_DIR / analysis_id / entry["html_file"]
    if not html_path.exists():
        raise HTTPException(404, "HTML file not found")

    content = html_path.read_text(encoding="utf-8")
    title   = entry.get("title", analysis_id)

    # Wrap legacy AI-generated fragments (no DOCTYPE) in a full document
    if not content.strip().lower().startswith("<!doctype"):
        content = (
            f'<!DOCTYPE html><html lang="zh"><head>'
            f'<meta charset="UTF-8"><title>{title}</title>'
            f'<style>body{{font-family:"PingFang SC","Microsoft YaHei",system-ui,sans-serif;'
            f'max-width:960px;margin:40px auto;padding:0 24px;color:#1f2937;line-height:1.8}}'
            f'table{{border-collapse:collapse;width:100%;margin:12px 0}}'
            f'td,th{{padding:8px 12px;border:1px solid #d1d5db}}'
            f'th{{background:#1e40af;color:white}}'
            f'h2{{color:#1e40af;border-bottom:2px solid #3b82f6;padding-bottom:8px}}'
            f'h3{{color:#374151;margin-top:16px}}</style>'
            f'</head><body>'
            f'<h1 style="color:#1e40af">{title}</h1>'
            f'{content}'
            f'</body></html>'
        )

    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=content)


@router.delete("/{analysis_id}")
async def delete_analysis(analysis_id: str):
    analysis_dir = ANALYSES_DIR / analysis_id
    if not analysis_dir.exists():
        raise HTTPException(404, "Analysis not found")
    import shutil
    shutil.rmtree(analysis_dir)
    index = [r for r in _load_index() if r["analysis_id"] != analysis_id]
    _save_index(index)
    return {"ok": True}


@router.post("/{analysis_id}/chat")
async def chat_about_analysis(analysis_id: str, req: ChatRequest):
    """Stream AI chat response about a saved analysis."""
    index = _load_index()
    entry = next((r for r in index if r["analysis_id"] == analysis_id), None)
    if not entry:
        raise HTTPException(404, "Analysis not found")

    html_path = ANALYSES_DIR / analysis_id / entry["html_file"]
    report_html = html_path.read_text(encoding="utf-8") if html_path.exists() else ""

    async def event_stream():
        try:
            async for chunk in chat_stream(
                report_html=report_html,
                message=req.message,
                history=req.history,
                api_key=req.api_key,
            ):
                yield f"data: {json.dumps({'type': 'chunk', 'text': chunk})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            return
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
