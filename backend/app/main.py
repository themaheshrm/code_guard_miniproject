from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api.routes import VERSION, router
from .config import get_settings
from .core.parsing import get_parser_diagnostics
from .db import init_db
from .services.analysis import build_engine
from .services.jobs import JobQueue

logger = logging.getLogger("codeguard")

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}
# Applied to the served single-page app (not to /docs, which loads Swagger UI from a CDN).
_SPA_CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' data: https://fonts.gstatic.com; img-src 'self' data: blob:; worker-src 'self' blob:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
_RATE_LIMITED = ("/api/v1/analyze", "/api/v1/jobs", "/api/v1/train", "/api/v1/benchmark")


class _RateLimiter:
    """Sliding one-minute window per client IP. In-memory: good enough for a single-process deployment."""

    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: str) -> bool:
        if self.per_minute <= 0:
            return True
        now = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= self.per_minute:
                return False
            q.append(now)
            if len(self.hits) > 10_000:
                self.hits.clear()
            return True


def create_app(database_url: str | None = None) -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db(database_url)
        orphans = JobQueue.recover_orphaned_jobs()
        if orphans:
            logger.warning("Recovered %d orphaned analysis job(s) from previous session.", orphans)

        diag = get_parser_diagnostics()
        missing = [lang for lang, d in diag.items() if not d.get("available")]
        if missing:
            logger.warning("Tree-sitter grammars unavailable for: %s. Multi-language AST features will be limited.", ", ".join(missing))

        app.state.settings = settings
        app.state.engine = build_engine(settings)
        app.state.jobs = JobQueue(app.state.engine, settings.job_workers)
        st = app.state.engine.ai.status()
        logger.info("AI engines: xgboost=%s codebert=%s heuristic=%s", st["xgboost"]["available"], st["codebert"]["available"],
                    st["heuristic"]["available"])
        yield
        app.state.jobs.shutdown(wait=True, cancel_futures=True)
        JobQueue.recover_orphaned_jobs("Server shut down before job could finish.")

    app = FastAPI(title="CodeGuard", version=VERSION, description="AI-assisted code integrity analyzer: AI-generated code, "
                  "plagiarism and vulnerability detection.", lifespan=lifespan)
    limiter = _RateLimiter(settings.rate_limit_per_minute)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        path = request.url.path
        if request.method in ("POST", "PUT", "PATCH"):
            try:
                length = int(request.headers.get("content-length") or 0)
            except ValueError:
                return JSONResponse({"detail": "Invalid Content-Length header."}, status_code=400)
            if length > settings.max_request_bytes:
                return JSONResponse({"detail": f"Request too large (max {settings.max_request_bytes} bytes)."}, status_code=413)
            if path.startswith(_RATE_LIMITED):
                ip = request.client.host if request.client else "unknown"
                if not limiter.allow(ip):
                    return JSONResponse({"detail": "Too many requests. Please wait a minute and try again."}, status_code=429,
                                        headers={"Retry-After": "60"})
        response = await call_next(request)
        for k, v in _SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        if not path.startswith(("/api", "/docs", "/redoc", "/openapi.json")):
            response.headers.setdefault("Content-Security-Policy", _SPA_CSP)
        return response

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):  # never leak a stack trace to the client
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse({"detail": f"Internal server error ({type(exc).__name__}). See server log for details."}, status_code=500)

    app.add_middleware(GZipMiddleware, minimum_size=2048)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
                       allow_headers=["Content-Type"])
    app.include_router(router)
    _mount_frontend(app, Path(settings.frontend_dist))
    return app


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    """Serve the production build (frontend/dist) so `uvicorn` alone runs the whole app on one port."""
    index = dist / "index.html"
    if not index.exists():
        @app.get("/", include_in_schema=False)
        def root():
            return {"name": "CodeGuard API", "version": VERSION, "docs": "/docs",
                    "hint": "Frontend build not found. Run `npm run build` in frontend/ or start the Vite dev server (port 5173)."}
        return
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
    root_dir = dist.resolve()

    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404, "Not found")
        candidate = (root_dir / full_path).resolve()
        if full_path and candidate.is_file() and root_dir in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


app = create_app()
