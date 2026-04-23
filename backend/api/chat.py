"""AI Chat API — intent parsing via Gemini."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ai.intent_parser import SearchIntent, intent_to_display_message, parse_intent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    history: list[dict]   # [{role: "user"|"assistant", content: "..."}]
    message: str
    api_key: Optional[str] = None   # override env key (BYOK)


class ChatResponse(BaseModel):
    intent: SearchIntent
    display_message: str   # text to show in the chat bubble
    ready: bool


@router.post("/message", response_model=ChatResponse)
async def chat_message(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(400, "Empty message")

    try:
        intent = await parse_intent(
            history=req.history,
            new_message=req.message,
            api_key=req.api_key or None,
        )
    except ValueError as e:
        raise HTTPException(500, str(e))
    except Exception as e:
        logger.error("Gemini parse failed: %s", e, exc_info=True)
        raise HTTPException(502, f"Gemini API error: {e}")

    if intent.ready_to_search:
        display_message = intent_to_display_message(intent)
    else:
        display_message = intent.clarifying_question or "请提供更多信息，以便我帮您搜索机票。"

    return ChatResponse(
        intent=intent,
        display_message=display_message,
        ready=intent.ready_to_search,
    )
