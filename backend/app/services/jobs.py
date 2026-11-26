"""Small in-process job queue (thread pool) backed by the analyses table, plus in-memory background tasks
(model training, benchmarks) whose status is polled by the UI."""
from __future__ import annotations

import datetime as dt
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from sqlalchemy import select

from ..db import Analysis, session
from ..schemas import AnalyzeRequest
from .analysis import Engine, run_analysis

logger = logging.getLogger("codeguard.jobs")


class JobQueue:
    def __init__(self, engine: Engine, workers: int):
        self.engine = engine
        self.pool = ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="cg-job")
        self.task_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cg-task")
        self.tasks: dict[str, dict] = {}
        self._tlock = threading.Lock()

    @staticmethod
    def recover_orphaned_jobs(reason: str = "Server was restarted while analysis was in progress.") -> int:
        """Find jobs that were left running or queued when the server stopped and mark them as failed."""
        with session() as db:
            orphans = db.scalars(select(Analysis).where(Analysis.status.in_(["running", "queued"]))).all()
            for a in orphans:
                a.status = "failed"
                a.error = reason
            if orphans:
                db.commit()
                logger.warning("Recovered %d orphaned analysis job(s) -> status=failed (%s)", len(orphans), reason)
            return len(orphans)

    def create(self, req: AnalyzeRequest) -> str:
        with session() as db:
            title = (req.title or "").strip() or (req.files[0].name if len(req.files) == 1 else f"Batch of {len(req.files)} files")
            a = Analysis(mode="batch" if len(req.files) > 1 else "single", n_files=len(req.files), persist=req.options.persist, title=title[:200])
            db.add(a)
            db.commit()
            return a.id

    def submit(self, analysis_id: str, req: AnalyzeRequest) -> None:
        self.pool.submit(self._run, analysis_id, req)

    def run_sync(self, analysis_id: str, req: AnalyzeRequest) -> None:
        self._run(analysis_id, req)

    def shutdown(self, wait: bool = True, cancel_futures: bool = True) -> None:
        self.pool.shutdown(wait=wait, cancel_futures=cancel_futures)
        self.task_pool.shutdown(wait=wait, cancel_futures=cancel_futures)

    def _run(self, analysis_id: str, req: AnalyzeRequest) -> None:
        self._set(analysis_id, status="running")
        try:
            result = run_analysis(self.engine, req, analysis_id)
            self._set(analysis_id, status="done", result=result, summary=result.get("summary"), finished_at=dt.datetime.now(dt.timezone.utc))
        except Exception as e:
            logger.exception("Analysis %s failed", analysis_id)
            self._set(analysis_id, status="failed", error=f"{type(e).__name__}: {e}", finished_at=dt.datetime.now(dt.timezone.utc))

    @staticmethod
    def _set(analysis_id: str, **fields) -> None:
        try:
            with session() as db:
                a = db.get(Analysis, analysis_id)
                if a is None:  # deleted while running
                    return
                for k, v in fields.items():
                    setattr(a, k, v)
                db.commit()
        except Exception as e:
            logger.error("Failed to update status for analysis %s: %s", analysis_id, e)

    # ------------------------------------------------------------------ background tasks
    def busy_task(self, kind: str) -> dict | None:
        with self._tlock:
            return next((t for t in self.tasks.values() if t["kind"] == kind and t["status"] in ("queued", "running")), None)

    def submit_task(self, kind: str, fn: Callable[[], dict]) -> dict:
        tid = uuid.uuid4().hex
        task = {"id": tid, "kind": kind, "status": "queued", "result": None, "error": None,
                "created_at": dt.datetime.now(dt.timezone.utc).isoformat()}
        with self._tlock:
            self.tasks[tid] = task
            if len(self.tasks) > 50:  # keep memory bounded
                for old in list(self.tasks)[:-50]:
                    self.tasks.pop(old, None)

        def run() -> None:
            task["status"] = "running"
            try:
                task["result"] = fn()
                task["status"] = "done"
            except SystemExit as e:  # training scripts signal bad data with SystemExit
                task["status"], task["error"] = "failed", str(e)
            except Exception as e:
                logger.exception("Task %s (%s) failed", tid, kind)
                task["status"], task["error"] = "failed", f"{type(e).__name__}: {e}"
            task["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()

        self.task_pool.submit(run)
        return task
