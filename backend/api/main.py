"""FastAPI app: routers, CORS, error handlers, /api/health."""
from __future__ import annotations

import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)  # local runs: pick up the gitignored .env; real env vars win

from fastapi import Depends, FastAPI, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from sqlalchemy import text  # noqa: E402

from api.deps import get_db  # noqa: E402
from api.routers import auth, batch, chat, contracts_api, master, policy, suppliers, workspace  # noqa: E402
from db.models import ImmutablePolicyError  # noqa: E402
from services import llm  # noqa: E402
from services.engine_adapter import active_version  # noqa: E402
from services.errors import ServiceError  # noqa: E402

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logging.getLogger("httpx").setLevel(logging.WARNING)  # request lines are noise; headers are never logged
log = logging.getLogger("corvo.api")

@asynccontextmanager
async def lifespan(_app):
    enabled, reason = llm.status()
    if enabled:
        log.info("LLM enabled=true model=%s", llm.model())
    else:
        log.info("LLM enabled=false reason=%s", reason)
    yield


app = FastAPI(title="Corvo PR-to-PO", version="1.0", lifespan=lifespan)

origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False, allow_methods=["*"],
                   allow_headers=["*"], expose_headers=["Content-Disposition"])

for r in (auth, batch, chat, contracts_api, master, policy, suppliers, workspace):
    app.include_router(r.router)


@app.exception_handler(ServiceError)
async def _service_error(request: Request, exc: ServiceError):
    return JSONResponse(status_code=exc.status, content={"detail": exc.detail})


@app.exception_handler(ImmutablePolicyError)
async def _immutable(request: Request, exc: ImmutablePolicyError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    ref = uuid.uuid4()
    log.error("Unhandled error ref=%s path=%s", ref, request.url.path, exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": f"Internal error, see server log (ref {ref})"})


@app.get("/api/health")
def health(db=Depends(get_db)):
    enabled, _ = llm.status()
    body = {"status": "ok", "db": "ok", "db_engine": db.get_bind().dialect.name, "active_policy": None,
            "llm": "enabled" if enabled else "disabled", "llm_model": llm.model()}
    try:
        db.execute(text("SELECT 1"))
        active = active_version(db)
        body["active_policy"] = active.version_label if active else None
    except Exception:  # noqa: BLE001 - any DB failure means unhealthy
        body.update(status="error", db="unavailable")
        return JSONResponse(status_code=503, content=body)
    return body
