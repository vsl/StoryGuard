import asyncio
import os
from contextlib import asynccontextmanager
from collections.abc import Awaitable, Callable

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.projects import router as projects_router
from app.db.session import engine
from app.health import readiness_payload


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(title="StoryGuard API", lifespan=lifespan)
app.include_router(projects_router)


async def _postgres_ready() -> None:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def _http_ready(url: str) -> None:
    async with httpx.AsyncClient(timeout=2) as client:
        response = await client.get(url)
        response.raise_for_status()


async def _passes(check: Callable[[], Awaitable[None]]) -> bool:
    try:
        await check()
    except Exception:
        return False
    return True


@app.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "alive"}


@app.get("/health/ready")
async def ready() -> JSONResponse:
    names = ("postgres", "minio", "elasticsearch")
    checks = await asyncio.gather(
        _passes(_postgres_ready),
        _passes(lambda: _http_ready(f"{os.environ['MINIO_URL']}/minio/health/live")),
        _passes(lambda: _http_ready(os.environ["ELASTICSEARCH_URL"])),
    )
    payload, status_code = readiness_payload(dict(zip(names, checks, strict=True)))
    return JSONResponse(payload, status_code=status_code)
