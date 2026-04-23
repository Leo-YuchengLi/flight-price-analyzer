"""Flight Price Analyzer — FastAPI backend entry point."""
import logging
import os
import sys

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = FastAPI(title="Flight Price Analyzer API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/ping")
async def ping():
    return {"ok": True, "version": "0.2.0"}


# ── Routers ───────────────────────────────────────────────────────────────────
from api.search    import router as search_router    # noqa: E402
from api.report    import router as report_router    # noqa: E402
from api.chat      import router as chat_router      # noqa: E402
from api.templates import router as templates_router # noqa: E402
from api.analysis  import router as analysis_router  # noqa: E402
from api.settings  import router as settings_router  # noqa: E402

app.include_router(search_router)
app.include_router(report_router)
app.include_router(chat_router)
app.include_router(templates_router)
app.include_router(analysis_router)
app.include_router(settings_router)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8765))
    print(f"PORT={port}", flush=True)
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=port,
        log_level="info",
        access_log=False,
    )
