"""Small in-process job queue (thread pool) backed by the analyses table."""
from __future__ import annotations

import traceback
from concurrent.futures import ThreadPoolExecutor

from ..db import Analysis, session
from ..schemas import AnalyzeRequest
from .analysis import Engine, run_analysis


class JobQueue:
    def __init__(self, engine: Engine, workers: int):
        self.engine = engine
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="cg-job")

    def create(self, req: AnalyzeRequest) -> str:
        with session() as db:
            a = Analysis(mode="batch" if len(req.files) > 1 else "single", n_files=len(req.files), persist=req.options.persist)
            db.add(a)
            db.commit()
            return a.id

    def submit(self, analysis_id: str, req: AnalyzeRequest) -> None:
        self.pool.submit(self._run, analysis_id, req)

    def run_sync(self, analysis_id: str, req: AnalyzeRequest) -> None:
        self._run(analysis_id, req)

    def _run(self, analysis_id: str, req: AnalyzeRequest) -> None:
        self._set(analysis_id, status="running")
        try:
            result = run_analysis(self.engine, req, analysis_id)
            self._set(analysis_id, status="done", result=result)
        except Exception as e:
            traceback.print_exc()
            self._set(analysis_id, status="failed", error=f"{type(e).__name__}: {e}")

    @staticmethod
    def _set(analysis_id: str, **fields) -> None:
        with session() as db:
            a = db.get(Analysis, analysis_id)
            if a is None:  # deleted while running
                return
            for k, v in fields.items():
                setattr(a, k, v)
            db.commit()
