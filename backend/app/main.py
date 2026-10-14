from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .config import get_settings
from .db import init_db
from .services.analysis import build_engine
from .services.jobs import JobQueue


def create_app(database_url: str | None = None) -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db(database_url)
        app.state.settings = settings
        app.state.engine = build_engine(settings)
        app.state.jobs = JobQueue(app.state.engine, settings.job_workers)
        yield
        app.state.jobs.pool.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(title="CodeGuard", version="1.0.0", description="AI-assisted code integrity analyzer", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_methods=["*"], allow_headers=["*"])
    app.include_router(router)
    return app


app = create_app()
