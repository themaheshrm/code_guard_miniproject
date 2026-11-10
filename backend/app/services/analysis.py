"""Orchestrates the three analysis modules into one verdict report."""
from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass

from sqlalchemy import select

from ..config import Settings
from ..core.parsing import detect_language
from ..db import Analysis, Submission, session
from ..detectors.ai_detector import AIDetector
from ..detectors.plagiarism import Fingerprint, PlagiarismConfig, build_fingerprint, clusters, compare, compare_batch
from ..detectors.vulnerability import VulnModel, analyze_vulnerabilities
from ..schemas import AnalyzeRequest

logger = logging.getLogger("codeguard.analysis")


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
    ai = AIDetector(settings.artifacts_dir, settings.ai_weight_xgb, settings.ai_weight_codebert, settings.enable_codebert)
    vuln = VulnModel(settings.artifacts_dir / "codebert_vuln") if settings.enable_vuln_model else None
    return Engine(settings, ai, vuln)


def _verdict(ai: dict | None, max_sim: float | None, risk: float | None, cfg: PlagiarismConfig) -> dict:
    flags = []
    if ai and ai.get("status") == "ok":
        p = ai["probability"]
        flags.append(("ai", "likely AI-generated" if p >= ai["threshold"] else "likely human-written", p >= ai["threshold"]))
    if max_sim is not None:
        flags.append(("similarity", "high similarity to another submission" if max_sim >= cfg.threshold else "no close match found", max_sim >= cfg.threshold))
    if risk is not None:
        flags.append(("security", "elevated security risk" if risk >= 50 else "low/moderate security risk", risk >= 50))
    n_flag = sum(f[2] for f in flags)
    level = "review" if n_flag >= 2 else "attention" if n_flag == 1 else "clear"
    return {
        "level": level, "signals": [{"signal": s, "summary": t, "flagged": f} for s, t, f in flags],
        "disclaimer": "Probabilistic decision-support output; not proof of misconduct. Review flagged items manually.",
    }


def run_analysis(engine: Engine, req: AnalyzeRequest, analysis_id: str | None = None) -> dict:
    s, opts, cfg = engine.settings, req.options, engine.plag_cfg
    files = []
    for f in req.files:
        lang = detect_language(f.name, f.code, f.language)
        files.append({"in": f, "language": lang})

    fps: list[Fingerprint] = []
    if opts.run_plagiarism or opts.persist:
        fps = [build_fingerprint(x["in"].name, x["in"].code, x["language"], cfg) for x in files]

    plag: dict | None = None
    max_sim: dict[str, float] = {}
    if opts.run_plagiarism:
        plag = compare_batch(fps, cfg) if len(fps) > 1 else {"names": [fps[0].name], "matrix": [[1.0]], "pairs": [], "clusters": []}
        for p in plag["pairs"]:
            for n in (p["a"], p["b"]):
                max_sim[n] = max(max_sim.get(n, 0.0), p["score"])
        plag["threshold"] = cfg.threshold
        if opts.compare_corpus:
            with session() as db:
                corpus = db.scalars(select(Submission).where(Submission.analysis_id != (analysis_id or ""))).all()
                ref_fps = [(c.name, c.id, Fingerprint.from_dict(c.fingerprint)) for c in corpus]
            corpus_hits = []
            for fp in fps:
                for ref_name, ref_id, rf in ref_fps:
                    if rf.language != fp.language:
                        continue
                    r = compare(fp, rf, cfg)
                    if r["score"] >= cfg.threshold * 0.6:
                        corpus_hits.append({**r, "reference_id": ref_id, "reference_name": ref_name})
                        max_sim[fp.name] = max(max_sim.get(fp.name, 0.0), r["score"])
            plag["corpus_matches"] = sorted(corpus_hits, key=lambda x: -x["score"])[:50]

    out_files = []
    for x, in_file in zip(files, [x["in"] for x in files]):
        code, lang = in_file.code, x["language"]
        entry: dict = {"name": in_file.name, "language": lang, "lines": code.count("\n") + 1}
        ai = engine.ai.predict(code, lang, explain=opts.explain) if opts.run_ai else None
        vuln = analyze_vulnerabilities(code, lang, engine.vuln) if opts.run_vulnerability else None
        entry["ai"], entry["vulnerability"] = ai, vuln
        entry["max_similarity"] = round(max_sim.get(in_file.name, 0.0), 4) if opts.run_plagiarism else None
        entry["verdict"] = _verdict(ai, entry["max_similarity"], vuln["risk_score"] if vuln else None, cfg)
        if len(code) < 400:
            entry["warnings"] = ["Very short input: AI-code and similarity estimates are unreliable for short or trivial snippets."]
        out_files.append(entry)

    report = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "options": opts.model_dump(),
        "files": out_files, "plagiarism": plag, "models": engine.ai.status(),
    }
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
