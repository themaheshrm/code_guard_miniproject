from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.parsing import get_parser_diagnostics
from ..db import Analysis, Submission, get_session, session
from ..schemas import AnalyzeRequest, FileIn, JobOut, Options

router = APIRouter(prefix="/api/v1")


def _out(a: Analysis, with_result: bool = True) -> JobOut:
    return JobOut(id=a.id, status=a.status, mode=a.mode, n_files=a.n_files, error=a.error,
                  result=a.result if with_result else None, created_at=a.created_at.isoformat() if a.created_at else None)


def _validate(req: AnalyzeRequest, request: Request) -> None:
    s = request.app.state.settings
    if len(req.files) > s.max_batch_files:
        raise HTTPException(413, f"Too many files (max {s.max_batch_files}).")
    for f in req.files:
        if len(f.code.encode("utf-8", errors="ignore")) > s.max_file_bytes:
            raise HTTPException(413, f"{f.name} exceeds {s.max_file_bytes} bytes.")
    names = [f.name for f in req.files]
    if len(set(names)) != len(names):
        raise HTTPException(422, "File names in one request must be unique.")


@router.get("/health")
def health(request: Request):
    return {
        "status": "ok",
        "models": request.app.state.engine.ai.status(),
        "parsers": get_parser_diagnostics(),
    }



@router.post("/analyze")
def analyze_sync(req: AnalyzeRequest, request: Request):
    """Synchronous analysis (intended for single files / small batches)."""
    _validate(req, request)
    q = request.app.state.jobs
    aid = q.create(req)
    q.run_sync(aid, req)
    with session() as db_session:
        a = db_session.get(Analysis, aid)
        if not a:
            raise HTTPException(404, "Analysis not found")
        if a.status == "failed":
            raise HTTPException(500, a.error)
        return _out(a)


@router.post("/jobs", status_code=202)
def create_job(req: AnalyzeRequest, request: Request):
    """Asynchronous analysis through the job queue; poll GET /jobs/{id}."""
    _validate(req, request)
    q = request.app.state.jobs
    aid = q.create(req)
    q.submit(aid, req)
    return {"id": aid, "status": "queued"}


@router.post("/jobs/upload", status_code=202)
async def create_job_upload(
    request: Request,
    files: list[UploadFile] = File(...),
    options: str = Form("{}"),
):
    try:
        opts = Options(**json.loads(options))
    except Exception as e:
        raise HTTPException(422, f"Invalid options JSON: {e}")
    items: list[FileIn] = []
    seen_names: dict[str, int] = {}
    for up in files:
        raw = await up.read()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
        if not text.strip():
            continue
        base_name = Path(up.filename or "upload").name
        if base_name in seen_names:
            seen_names[base_name] += 1
            p = Path(base_name)
            final_name = f"{p.stem}_{seen_names[base_name]}{p.suffix}"
        else:
            seen_names[base_name] = 0
            final_name = base_name
        items.append(FileIn(name=final_name, code=text))
    if not items:
        raise HTTPException(422, "No non-empty files uploaded.")
    req = AnalyzeRequest(files=items, options=opts)
    _validate(req, request)
    q = request.app.state.jobs
    aid = q.create(req)
    q.submit(aid, req)
    return {"id": aid, "status": "queued"}


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, db: Session = Depends(get_session)):
    a = db.get(Analysis, job_id)
    if not a:
        raise HTTPException(404, "Job not found")
    return _out(a)


@router.get("/analyses", response_model=list[JobOut])
def list_analyses(limit: int = 50, db: Session = Depends(get_session)):
    rows = db.scalars(select(Analysis).order_by(Analysis.created_at.desc()).limit(min(limit, 200))).all()
    return [_out(a, with_result=False) for a in rows]


@router.delete("/analyses/{analysis_id}", status_code=204)
def delete_analysis(analysis_id: str, db: Session = Depends(get_session)):
    a = db.get(Analysis, analysis_id)
    if not a:
        raise HTTPException(404, "Analysis not found")
    db.query(Submission).filter(Submission.analysis_id == analysis_id).delete()
    db.delete(a)
    db.commit()


@router.get("/corpus")
def corpus(db: Session = Depends(get_session)):
    rows = db.scalars(select(Submission).order_by(Submission.created_at.desc()).limit(500)).all()
    return [{"id": r.id, "name": r.name, "language": r.language, "created_at": r.created_at.isoformat(), "analysis_id": r.analysis_id} for r in rows]


@router.delete("/corpus/{submission_id}", status_code=204)
def delete_submission(submission_id: str, db: Session = Depends(get_session)):
    r = db.get(Submission, submission_id)
    if not r:
        raise HTTPException(404, "Submission not found")
    db.delete(r)
    db.commit()


@router.get("/metrics")
def metrics(request: Request):
    """Evaluation artefacts written by the training scripts (confusion matrices, ROC, feature importance)."""
    d: Path = request.app.state.settings.artifacts_dir
    out = {}
    for key, rel in {"xgboost": "xgb_ai_metrics.json", "codebert": "codebert_ai/metrics.json",
                     "vulnerability": "codebert_vuln/metrics.json", "plagiarism": "plagiarism_metrics.json"}.items():
        p = d / rel
        out[key] = json.loads(p.read_text()) if p.exists() else None
    return out
