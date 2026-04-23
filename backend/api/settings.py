"""Settings API — runtime configuration (API keys, etc.)."""
from __future__ import annotations

import os
import logging

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings", tags=["settings"])


class TestKeyRequest(BaseModel):
    api_key: str


class ApiKeyRequest(BaseModel):
    api_key: str


@router.post("/api-key")
async def set_api_key(req: ApiKeyRequest):
    """Update the Gemini API key at runtime (no restart needed)."""
    if req.api_key:
        os.environ["GEMINI_API_KEY"] = req.api_key
        logger.info("GEMINI_API_KEY updated via settings API")
        return {"ok": True}
    return {"ok": False, "message": "Empty key ignored"}


@router.get("/api-key/status")
async def api_key_status():
    """Check whether a Gemini API key is currently configured."""
    key = os.environ.get("GEMINI_API_KEY", "")
    return {
        "configured": bool(key),
        "preview": f"{key[:8]}…" if len(key) > 8 else ("(empty)" if not key else key),
    }


@router.post("/test-api-key")
async def test_api_key(req: TestKeyRequest):
    """Actually call the Gemini API to verify the key is valid."""
    key = req.api_key.strip()
    if not key:
        return {"ok": False, "message": "API Key 为空"}
    try:
        from google import genai  # type: ignore
        client = genai.Client(api_key=key)
        models = list(client.models.list())
        return {"ok": True, "message": f"连接成功，共找到 {len(models)} 个可用模型"}
    except Exception as e:
        err = str(e)
        if "API_KEY_INVALID" in err or "invalid" in err.lower() or "401" in err:
            return {"ok": False, "message": "API Key 无效，请检查是否填写正确"}
        if "403" in err or "permission" in err.lower():
            return {"ok": False, "message": "API Key 无访问权限"}
        logger.warning("Gemini test failed: %s", e)
        return {"ok": False, "message": f"连接失败：{err[:120]}"}
