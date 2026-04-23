"""Route template CRUD — save and load frequently used search routes."""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/templates", tags=["templates"])

DATA_DIR = Path(__file__).parent.parent / "data"
TMPL_FILE = DATA_DIR / "templates.json"


class TemplateCreate(BaseModel):
    name: str
    origin: str
    destination: str
    date_start: str = ""
    date_end: str = ""
    cabin: str = "Y"
    currency: str = "EUR"


class Template(TemplateCreate):
    id: str
    created_at: str


def _load() -> list[dict]:
    if not TMPL_FILE.exists():
        return []
    return json.loads(TMPL_FILE.read_text(encoding="utf-8"))


def _save(data: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TMPL_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


@router.get("")
async def list_templates():
    return _load()


@router.post("", response_model=Template)
async def create_template(req: TemplateCreate):
    templates = _load()
    tmpl = {
        "id": uuid.uuid4().hex[:8],
        "name": req.name,
        "origin": req.origin.upper(),
        "destination": req.destination.upper(),
        "date_start": req.date_start,
        "date_end": req.date_end,
        "cabin": req.cabin,
        "currency": req.currency,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    templates.insert(0, tmpl)
    _save(templates)
    return tmpl


@router.delete("/{template_id}")
async def delete_template(template_id: str):
    templates = _load()
    updated = [t for t in templates if t["id"] != template_id]
    if len(updated) == len(templates):
        raise HTTPException(404, "Template not found")
    _save(updated)
    return {"ok": True}
