"""Orchestrates the three analysis modules into one verdict report."""
from __future__ import annotations

import datetime as dt
import logging
import time
from dataclasses import dataclass

from sqlalchemy import select

from ..config import Settings
from ..core.parsing import detect_language
from ..db import Analysis, Submission, session
from ..detectors.ai_detector import AIDetector
from ..detectors.plagiarism import Fingerprint, PlagiarismConfig, build_fingerprint, clusters, compare
from ..detectors.vulnerability import VulnModel, analyze_vulnerabilities
from ..schemas import AnalyzeRequest

logger = logging.getLogger("codeguard.analysis")
LEVEL_RANK = {"clear": 0, "attention": 1, "review": 2}


@dataclass
class Engine:
    settings: Settings
    ai: AIDetector
    vuln: VulnModel | None

    @property
    def plag_cfg(self) -> PlagiarismConfig:
        s = self.settings
        return PlagiarismConfig(s.winnow_k, s.winnow_w, s.ast_min_subtree, s.token_weight, s.plagiarism_threshold)


def build_engine(settings: Settings) -> Engine:
    ai = AIDetector(settings.artifacts_dir, settings.ai_weight_xgb, settings.ai_weight_codebert, settings.enable_codebert,
                    settings.enable_heuristic, settings.ai_weight_heuristic)
    vuln = VulnModel(settings.artifacts_dir / "codebert_vuln") if settings.enable_vuln_model else None
    return Engine(settings, ai, vuln)


def _verdict(ai: dict | None, max_sim: float | None, risk: float | None, cfg: PlagiarismConfig) -> dict:
    flags = []
    if ai and ai.get("status") == "ok":
        p, thr = ai["probability"], ai["threshold"]
        flags.append(("ai", f"likely AI-generated ({round(p * 100)}%, {ai.get('confidence', 'low')} confidence)" if p >= thr
                      else f"likely human-written ({round(p * 100)}% AI)", p >= thr))
    if max_sim is not None:
        flags.append(("similarity", f"high similarity to another submission ({round(max_sim * 100)}%)" if max_sim >= cfg.threshold
                      else "no close match found", max_sim >= cfg.threshold))
    if risk is not None:
        flags.append(("security", f"elevated security risk (score {risk:g}/100)" if risk >= 50
                      else "low security risk" if risk < 20 else f"moderate security risk (score {risk:g}/100)", risk >= 50))
    n_flag = sum(f[2] for f in flags)
    level = "review" if n_flag >= 2 else "attention" if n_flag == 1 else "clear"
    return {
        "level": level, "signals": [{"signal": s, "summary": t, "flagged": f} for s, t, f in flags],
        "disclaimer": "Probabilistic decision-support output; not proof of misconduct. Review flagged items manually.",
    }


def summarize(report: dict) -> dict:
    """Compact numbers used by the history list and the dashboard (no code, no snippets)."""
    files = report.get("files", [])
    ai_probs = [f["ai"]["probability"] for f in files if f.get("ai") and f["ai"].get("status") == "ok"]
    risks = [f["vulnerability"]["risk_score"] for f in files if f.get("vulnerability")]
    sev: dict[str, int] = {}
    cwes: dict[str, int] = {}
    for f in files:
        v = f.get("vulnerability") or {}
        for x in v.get("findings", []):
            sev[x["severity"]] = sev.get(x["severity"], 0) + 1
            cwes[x["cwe"]] = cwes.get(x["cwe"], 0) + 1
    levels = [f["verdict"]["level"] for f in files if f.get("verdict")]
    plag = report.get("plagiarism") or {}
    langs: dict[str, int] = {}
    for f in files:
        langs[f["language"]] = langs.get(f["language"], 0) + 1
    return {
        "n_files": len(files),
        "languages": langs,
        "level": max(levels, key=lambda lv: LEVEL_RANK[lv]) if levels else "clear",
        "levels": {lv: levels.count(lv) for lv in LEVEL_RANK},
        "ai_flagged": sum(1 for f in files if (f.get("ai") or {}).get("label") == "ai"),
        "ai_mean": round(sum(ai_probs) / len(ai_probs), 4) if ai_probs else None,
        "ai_max": round(max(ai_probs), 4) if ai_probs else None,
        "similar_pairs": sum(1 for p in plag.get("pairs", []) if p.get("flagged")),
        "max_similarity": round(max((f.get("max_similarity") or 0.0) for f in files), 4) if files else 0.0,
        "risk_max": max(risks) if risks else None,
        "high_risk_files": sum(1 for r in risks if r >= 50),
        "findings": sum(sev.values()),
        "severity": sev,
        "cwes": cwes,
        "names": [f["name"] for f in files][:20],
    }


def _plagiarism(fps: list[Fingerprint], cfg: PlagiarismConfig) -> dict:
    n = len(fps)
    matrix = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    pairs: list[dict] = []
    for i in range(n):
        for j in range(i + 1, n):
            if fps[i].language != fps[j].language:
                continue  # token/AST fingerprints are not comparable across languages
            r = compare(fps[i], fps[j], cfg)
            matrix[i][j] = matrix[j][i] = r["score"]
            pairs.append(r)
    pairs.sort(key=lambda p: -p["score"])
    return {"names": [f.name for f in fps], "languages": [f.language for f in fps], "matrix": matrix, "pairs": pairs,
            "clusters": clusters(fps, matrix, cfg.threshold)}


def run_analysis(engine: Engine, req: AnalyzeRequest, analysis_id: str | None = None) -> dict:
    t0 = time.perf_counter()
    opts, cfg = req.options, engine.plag_cfg
    files = [{"in": f, "language": detect_language(f.name, f.code, f.language)} for f in req.files]

    fps: list[Fingerprint] = []
    if opts.run_plagiarism or opts.persist:
        fps = [build_fingerprint(x["in"].name, x["in"].code, x["language"], cfg) for x in files]

    plag: dict | None = None
    max_sim: dict[str, float] = {}
    if opts.run_plagiarism:
        plag = _plagiarism(fps, cfg)
        for p in plag["pairs"]:
            for n in (p["a"], p["b"]):
                max_sim[n] = max(max_sim.get(n, 0.0), p["score"])
        plag["threshold"] = cfg.threshold
        if opts.compare_corpus:
            langs = {fp.language for fp in fps}
            with session() as db:
                q = select(Submission).where(Submission.language.in_(langs))
                if analysis_id:
                    q = q.where(Submission.analysis_id != analysis_id)
                corpus = db.scalars(q.order_by(Submission.created_at.desc()).limit(2000)).all()
                ref_fps = [(c.name, c.id, c.analysis_id, Fingerprint.from_dict(c.fingerprint)) for c in corpus]
            corpus_hits = []
            for fp in fps:
                for ref_name, ref_id, ref_aid, rf in ref_fps:
                    if rf.language != fp.language:
                        continue
                    r = compare(fp, rf, cfg)
                    if r["score"] >= cfg.threshold * 0.6:
                        corpus_hits.append({**r, "reference_id": ref_id, "reference_name": ref_name, "reference_analysis": ref_aid})
                        max_sim[fp.name] = max(max_sim.get(fp.name, 0.0), r["score"])
            plag["corpus_matches"] = sorted(corpus_hits, key=lambda x: -x["score"])[:50]
            plag["corpus_size"] = len(ref_fps)

    out_files = []
    for x in files:
        in_file, lang = x["in"], x["language"]
        code = in_file.code
        fp = next((f for f in fps if f.name == in_file.name), None)
        entry: dict = {"name": in_file.name, "language": lang, "lines": code.count("\n") + 1, "chars": len(code),
                       "parsed": fp.ast_ok if fp else None}
        ai = engine.ai.predict(code, lang, explain=opts.explain) if opts.run_ai else None
        vuln = analyze_vulnerabilities(code, lang, engine.vuln) if opts.run_vulnerability else None
        entry["ai"], entry["vulnerability"] = ai, vuln
        entry["max_similarity"] = round(max_sim.get(in_file.name, 0.0), 4) if opts.run_plagiarism else None
        entry["verdict"] = _verdict(ai, entry["max_similarity"], vuln["risk_score"] if vuln else None, cfg)
        warnings = []
        if len(code) < 400:
            warnings.append("Very short input: AI-code and similarity estimates are unreliable for short or trivial snippets.")
        if fp is not None and not fp.ast_ok:
            warnings.append("The file could not be fully parsed (syntax error or unsupported construct); structural analysis fell back to tokens.")
        if ai and ai.get("status") == "ok" and ai.get("engine") == "heuristic":
            warnings.append("AI score comes from the heuristic style engine only. Polished, well-documented human code can also score high.")
        if warnings:
            entry["warnings"] = warnings
        out_files.append(entry)

    report = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "options": opts.model_dump(), "title": req.title,
        "files": out_files, "plagiarism": plag, "models": engine.ai.status(),
        "duration_ms": round((time.perf_counter() - t0) * 1000, 1),
    }
    report["summary"] = summarize(report)
    if opts.persist and analysis_id:
        with session() as db:
            a = db.get(Analysis, analysis_id)
            if a is not None:  # Ensure analysis has not been concurrently deleted
                for x, fp in zip(files, fps):
                    db.add(Submission(analysis_id=analysis_id, name=x["in"].name, language=x["language"], sha256=fp.sha256,
                                      code=x["in"].code, fingerprint=fp.to_dict()))
                try:
                    db.commit()
                except Exception as e:
                    db.rollback()
                    logger.warning("Could not persist submissions for analysis %s: %s", analysis_id, e)
    return report
