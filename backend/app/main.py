from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .config import get_settings
from .core.parsing import get_parser_diagnostics
from .db import init_db
from .services.analysis import build_engine
from .services.jobs import JobQueue

logger = logging.getLogger("codeguard")


def create_app(database_url: str | None = None) -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db(database_url)
        orphans = JobQueue.recover_orphaned_jobs()
        if orphans:
            logger.warning("Recovered %d orphaned analysis job(s) from previous session.", orphans)

        diag = get_parser_diagnostics()
        missing = [l for l, d in diag.items() if not d.get("available")]
        if missing:
            logger.warning(
                "Tree-sitter grammars unavailable for: %s. Multi-language AST features will be limited.",
                ", ".join(missing),
            )

        app.state.settings = settings
        app.state.engine = build_engine(settings)
        app.state.jobs = JobQueue(app.state.engine, settings.job_workers)
        yield
        app.state.jobs.shutdown(wait=True, cancel_futures=True)
        JobQueue.recover_orphaned_jobs("Server shut down before job could finish.")

    app = FastAPI(title="CodeGuard", version="1.0.0", description="AI-assisted code integrity analyzer", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_methods=["*"], allow_headers=["*"])
    app.include_router(router)
    return app


app = create_app()

