from __future__ import annotations

import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from ..config import BACKEND_DIR
from ..core.parsing import SUPPORTED_LANGUAGES, get_parser_diagnostics
from ..db import Analysis, Submission, as_utc, get_session, session
from ..detectors.vulnerability import RULES
from ..schemas import AnalyzeRequest, FileIn, JobOut, Options
from ..services.analysis import summarize

router = APIRouter(prefix="/api/v1")
VERSION = "2.0.0"
_STARTED = dt.datetime.now(dt.timezone.utc)
MAX_TRAIN_BYTES = 60_000_000


def _iso(d: dt.datetime | None) -> str | None:
    d = as_utc(d)
    return d.isoformat() if d else None


def _out(a: Analysis, with_result: bool = True) -> JobOut:
    return JobOut(id=a.id, status=a.status, mode=a.mode, n_files=a.n_files, title=a.title, error=a.error,
                  result=a.result if with_result else None, summary=a.summary,
                  created_at=_iso(a.created_at), finished_at=_iso(a.finished_at))


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


def _ensure_ml_importable() -> None:
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))


# ------------------------------------------------------------------------------------------------ status
@router.get("/health")
def health(request: Request, db: Session = Depends(get_session)):
    eng = request.app.state.engine
    return {
        "status": "ok",
        "version": VERSION,
        "uptime_seconds": int((dt.datetime.now(dt.timezone.utc) - _STARTED).total_seconds()),
        "models": eng.ai.status(),
        "vulnerability_model": {"available": bool(eng.vuln and eng.vuln.available),
                                "error": (eng.vuln.error if eng.vuln else "disabled")},
        "parsers": get_parser_diagnostics(),
        "languages": list(SUPPORTED_LANGUAGES),
        "rules": len(RULES),
        "counts": {"analyses": db.scalar(select(func.count()).select_from(Analysis)) or 0,
                   "corpus": db.scalar(select(func.count()).select_from(Submission)) or 0},
        "limits": {"max_file_bytes": request.app.state.settings.max_file_bytes,
                   "max_batch_files": request.app.state.settings.max_batch_files},
        "plagiarism_threshold": request.app.state.settings.plagiarism_threshold,
    }


@router.get("/rules")
def rules(language: str | None = None):
    """The static-analysis rule catalogue (CWE, OWASP category, severity, remediation)."""
    out = [r.to_dict() for r in RULES if language is None or language in r.languages]
    return {"count": len(out), "rules": out}


# ------------------------------------------------------------------------------------------------ analysis
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


async def _read_limited(up: UploadFile, limit: int) -> bytes:
    raw = await up.read(limit + 1)
    if len(raw) > limit:
        raise HTTPException(413, f"{up.filename} exceeds {limit} bytes.")
    return raw


@router.post("/jobs/upload", status_code=202)
async def create_job_upload(
    request: Request,
    files: list[UploadFile] = File(...),
    options: str = Form("{}"),
    title: str | None = Form(None),
):
    s = request.app.state.settings
    try:
        opts = Options(**json.loads(options or "{}"))
    except Exception as e:
        raise HTTPException(422, f"Invalid options JSON: {e}")
    if len(files) > s.max_batch_files:
        raise HTTPException(413, f"Too many files (max {s.max_batch_files}).")
    items: list[FileIn] = []
    seen_names: dict[str, int] = {}
    for up in files:
        raw = await _read_limited(up, s.max_file_bytes)
        if b"\x00" in raw[:4096]:
            continue  # binary file
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
        if not text.strip():
            continue
        base_name = Path((up.filename or "upload").replace("\\", "/")).name or "upload"
        if base_name in seen_names:
            seen_names[base_name] += 1
            p = Path(base_name)
            final_name = f"{p.stem}_{seen_names[base_name]}{p.suffix}"
        else:
            seen_names[base_name] = 0
            final_name = base_name
        items.append(FileIn(name=final_name, code=text))
    if not items:
        raise HTTPException(422, "No non-empty text files uploaded.")
    try:
        req = AnalyzeRequest(files=items, options=opts, title=title)
    except ValidationError as e:
        raise HTTPException(422, str(e))
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


# ------------------------------------------------------------------------------------------------ history
@router.get("/analyses", response_model=list[JobOut])
def list_analyses(limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0), q: str | None = None,
                  status: str | None = None, db: Session = Depends(get_session)):
    stmt = select(Analysis)
    if status:
        stmt = stmt.where(Analysis.status == status)
    if q:
        stmt = stmt.where(or_(Analysis.title.ilike(f"%{q}%"), Analysis.id.ilike(f"{q}%")))
    rows = db.scalars(stmt.order_by(Analysis.created_at.desc()).offset(offset).limit(limit)).all()
    return [_out(a, with_result=False) for a in rows]


@router.get("/analyses/{analysis_id}/export")
def export_analysis(analysis_id: str, db: Session = Depends(get_session)):
    a = db.get(Analysis, analysis_id)
    if not a:
        raise HTTPException(404, "Analysis not found")
    body = json.dumps(_out(a).model_dump(), indent=2)
    return Response(body, media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="codeguard-report-{analysis_id[:8]}.json"'})


@router.delete("/analyses/{analysis_id}", status_code=204)
def delete_analysis(analysis_id: str, db: Session = Depends(get_session)):
    a = db.get(Analysis, analysis_id)
    if not a:
        raise HTTPException(404, "Analysis not found")
    db.execute(delete(Submission).where(Submission.analysis_id == analysis_id))
    db.delete(a)
    db.commit()


@router.delete("/analyses", status_code=204)
def clear_history(include_corpus: bool = False, db: Session = Depends(get_session)):
    """Delete every finished/failed analysis. Saved corpus submissions are kept unless include_corpus=true."""
    keep_ids = set()
    if not include_corpus:
        keep_ids = set(db.scalars(select(Submission.analysis_id).distinct()).all())
    else:
        db.execute(delete(Submission))
    stmt = delete(Analysis).where(Analysis.status.in_(["done", "failed"]))
    if keep_ids:
        stmt = stmt.where(Analysis.id.not_in(keep_ids))
    db.execute(stmt)
    db.commit()


@router.get("/stats")
def stats(days: int = Query(14, ge=1, le=90), db: Session = Depends(get_session)):
    """Aggregates for the dashboard, computed from per-analysis summaries (never from stored code)."""
    rows = db.scalars(select(Analysis).order_by(Analysis.created_at.desc()).limit(2000)).all()
    today = dt.datetime.now(dt.timezone.utc).date()
    timeline = {(today - dt.timedelta(days=i)).isoformat(): {"analyses": 0, "files": 0, "flagged": 0} for i in range(days - 1, -1, -1)}
    totals = Counter()
    langs, levels, sev, cwes = Counter(), Counter(), Counter(), Counter()
    ai_probs: list[float] = []
    backfilled = False
    recent = []
    for a in rows:
        totals["analyses"] += 1
        totals[a.status] += 1
        if a.status != "done":
            continue
        summ = a.summary
        if summ is None and a.result:
            summ = a.summary = summarize(a.result)  # rows created before summaries existed
            backfilled = True
        if not summ:
            continue
        totals["files"] += summ["n_files"]
        totals["ai_flagged"] += summ["ai_flagged"]
        totals["similar_pairs"] += summ["similar_pairs"]
        totals["high_risk_files"] += summ["high_risk_files"]
        totals["findings"] += summ["findings"]
        langs.update(summ.get("languages", {}))
        levels.update(summ.get("levels", {}))
        sev.update(summ.get("severity", {}))
        cwes.update(summ.get("cwes", {}))
        if summ.get("ai_mean") is not None:
            ai_probs.append(summ["ai_mean"])
        day = as_utc(a.created_at).date().isoformat()
        if day in timeline:
            timeline[day]["analyses"] += 1
            timeline[day]["files"] += summ["n_files"]
            timeline[day]["flagged"] += summ["levels"].get("review", 0) + summ["levels"].get("attention", 0)
        if len(recent) < 8:
            recent.append({"id": a.id, "title": a.title, "created_at": _iso(a.created_at), "n_files": a.n_files, "summary": summ})
    if backfilled:
        db.commit()
    return {
        "totals": {k: totals.get(k, 0) for k in ("analyses", "done", "failed", "running", "queued", "files", "ai_flagged",
                                                  "similar_pairs", "high_risk_files", "findings")},
        "ai_mean": round(sum(ai_probs) / len(ai_probs), 4) if ai_probs else None,
        "languages": dict(langs.most_common()),
        "verdicts": {k: levels.get(k, 0) for k in ("clear", "attention", "review")},
        "severity": {k: sev.get(k, 0) for k in ("critical", "high", "medium", "low")},
        "top_cwes": [{"cwe": c, "count": n} for c, n in cwes.most_common(8)],
        "timeline": [{"date": d, **v} for d, v in timeline.items()],
        "recent": recent,
        "corpus_size": db.scalar(select(func.count()).select_from(Submission)) or 0,
    }


# ------------------------------------------------------------------------------------------------ corpus
@router.get("/corpus")
def corpus(db: Session = Depends(get_session)):
    rows = db.scalars(select(Submission).order_by(Submission.created_at.desc()).limit(500)).all()
    return [{"id": r.id, "name": r.name, "language": r.language, "created_at": _iso(r.created_at), "analysis_id": r.analysis_id,
             "lines": r.code.count("\n") + 1, "sha256": r.sha256} for r in rows]


@router.get("/corpus/{submission_id}")
def corpus_item(submission_id: str, db: Session = Depends(get_session)):
    r = db.get(Submission, submission_id)
    if not r:
        raise HTTPException(404, "Submission not found")
    return {"id": r.id, "name": r.name, "language": r.language, "created_at": _iso(r.created_at), "analysis_id": r.analysis_id, "code": r.code}


@router.delete("/corpus/{submission_id}", status_code=204)
def delete_submission(submission_id: str, db: Session = Depends(get_session)):
    r = db.get(Submission, submission_id)
    if not r:
        raise HTTPException(404, "Submission not found")
    db.delete(r)
    db.commit()


# ------------------------------------------------------------------------------------------------ models
@router.get("/metrics")
def metrics(request: Request):
    """Evaluation artefacts written by the training scripts (confusion matrices, ROC, feature importance)."""
    d: Path = request.app.state.settings.artifacts_dir
    out = {}
    for key, rel in {"xgboost": "xgb_ai_metrics.json", "codebert": "codebert_ai/metrics.json",
                     "vulnerability": "codebert_vuln/metrics.json", "plagiarism": "plagiarism_metrics.json"}.items():
        p = d / rel
        try:
            out[key] = json.loads(p.read_text()) if p.exists() else None
        except (OSError, json.JSONDecodeError):
            out[key] = None
    return out


@router.post("/models/reload")
def reload_models(request: Request):
    return request.app.state.engine.ai.reload()


def _parse_training_rows(raw: bytes) -> list[dict]:
    rows: list[dict] = []
    for no, line in enumerate(raw.decode("utf-8-sig", errors="replace").splitlines(), 1):
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            raise HTTPException(422, f"Line {no}: not valid JSON.")
        if not isinstance(r, dict) or not isinstance(r.get("code"), str) or r.get("label") not in (0, 1, "0", "1", True, False):
            raise HTTPException(422, f"Line {no}: each row needs a string 'code' and a 'label' of 0 (human) or 1 (AI).")
        lang = (r.get("language") or "python").lower()
        if lang not in SUPPORTED_LANGUAGES:
            raise HTTPException(422, f"Line {no}: unsupported language '{lang}'.")
        rid = str(r.get("id") or f"row{no}")
        rows.append({**r, "id": rid, "group_id": str(r.get("group_id") or rid), "label": int(r["label"]), "language": lang})
        if len(rows) > 50_000:
            raise HTTPException(413, "Too many rows (max 50,000).")
    labels = {r["label"] for r in rows}
    if len(rows) < 20 or labels != {0, 1}:
        raise HTTPException(422, "Need at least 20 rows containing both human (0) and AI (1) examples.")
    return rows


@router.post("/train/xgboost", status_code=202)
async def train_xgboost(request: Request, dataset: UploadFile = File(...), max_fpr: float = Form(0.05)):
    """Train the XGBoost detector from an uploaded JSONL dataset, then hot-reload it into the running API."""
    if not 0 < max_fpr < 1:
        raise HTTPException(422, "max_fpr must be between 0 and 1.")
    q = request.app.state.jobs
    if q.busy_task("train_xgboost"):
        raise HTTPException(409, "A training run is already in progress.")
    rows = _parse_training_rows(await _read_limited(dataset, MAX_TRAIN_BYTES))
    _ensure_ml_importable()
    from ml.train_xgboost import train

    engine, out_dir = request.app.state.engine, request.app.state.settings.artifacts_dir

    def job() -> dict:
        m = train(rows, Path(out_dir), max_fpr=max_fpr, quiet=True)
        engine.ai.reload()
        return {"rows": len(rows), "test": {k: v for k, v in (m.get("test") or {}).items() if k not in ("roc_curve",)},
                "split_sizes": m.get("split_sizes")}

    return q.submit_task("train_xgboost", job)


@router.post("/benchmark/plagiarism", status_code=202)
def benchmark_plagiarism(request: Request, n: int = Query(100, ge=10, le=400)):
    """Recall on obfuscated copies of real Python stdlib functions vs. unrelated pairs; writes plagiarism_metrics.json."""
    q = request.app.state.jobs
    if q.busy_task("benchmark_plagiarism"):
        raise HTTPException(409, "A benchmark is already running.")
    _ensure_ml_importable()
    from ml.eval_plagiarism import evaluate, stdlib_functions

    eng, out = request.app.state.engine, request.app.state.settings.artifacts_dir / "plagiarism_metrics.json"

    def job() -> dict:
        programs = stdlib_functions(n)
        if len(programs) < 10:
            raise RuntimeError("Could not collect enough stdlib functions for the benchmark.")
        res = evaluate(programs, eng.plag_cfg)
        res["corpus"] = "python stdlib functions (sanity check)"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(res, indent=2))
        return {k: res[k] for k in ("n_programs", "recall_at_threshold", "negative_fpr_at_threshold")}

    return q.submit_task("benchmark_plagiarism", job)


@router.get("/tasks/{task_id}")
def get_task(task_id: str, request: Request):
    t = request.app.state.jobs.tasks.get(task_id)
    if not t:
        raise HTTPException(404, "Task not found")
    return t
