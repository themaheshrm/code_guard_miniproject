"""Plagiarism evaluation: precision/recall on synthetically obfuscated copies (identifier renaming, statement
reordering, comment edits, dead-code insertion, and all combined) vs. negative pairs of different programs.

    python -m ml.eval_plagiarism --data data/datasets/ai_dataset.jsonl          # human python solutions, one per problem
    python -m ml.eval_plagiarism --stdlib                                       # sanity check on stdlib functions
"""
from __future__ import annotations

import argparse
import ast
import json
import random
import sysconfig
from pathlib import Path

from app.detectors.plagiarism import PlagiarismConfig, build_fingerprint, compare

from .common import ARTIFACTS, read_jsonl
from .obfuscate import TRANSFORMS, combined


def stdlib_functions(limit: int = 150, seed: int = 0) -> list[str]:
    rng = random.Random(seed)
    files = sorted(Path(sysconfig.get_paths()["stdlib"]).glob("*.py"))
    rng.shuffle(files)
    out: list[str] = []
    for f in files:
        try:
            src = f.read_text(errors="ignore")
            tree = ast.parse(src)
        except (SyntaxError, ValueError):
            continue
        for n in tree.body:
            if isinstance(n, ast.FunctionDef) and 10 <= (n.end_lineno - n.lineno + 1) <= 80:
                seg = ast.get_source_segment(src, n)
                if seg:
                    out.append(seg + "\n")
        if len(out) >= limit * 3:
            break
    rng.shuffle(out)
    return out[:limit]


def evaluate(programs: list[str], cfg: PlagiarismConfig, seed: int = 1, n_neg: int = 400) -> dict:
    rng = random.Random(seed)
    kinds = {**TRANSFORMS, "combined": combined}
    pos_scores: dict[str, list[float]] = {k: [] for k in kinds}
    for src in programs:
        base = build_fingerprint("o", src, "python", cfg)
        for k, fn in kinds.items():
            try:
                variant = fn(src, rng)
            except Exception:
                continue
            pos_scores[k].append(compare(base, build_fingerprint("v", variant, "python", cfg), cfg)["score"])
    fps = [build_fingerprint(str(i), p, "python", cfg) for i, p in enumerate(programs)]
    neg = []
    for _ in range(n_neg):
        i, j = rng.sample(range(len(fps)), 2)
        neg.append(compare(fps[i], fps[j], cfg)["score"])
    allpos = [s for v in pos_scores.values() for s in v]
    sweep = []
    for t in [x / 20 for x in range(2, 20)]:
        tp = sum(s >= t for s in allpos)
        fp = sum(s >= t for s in neg)
        prec = tp / (tp + fp) if tp + fp else 1.0
        rec = tp / len(allpos) if allpos else 0.0
        sweep.append({"threshold": t, "precision": round(prec, 4), "recall": round(rec, 4),
                      "f1": round(2 * prec * rec / (prec + rec), 4) if prec + rec else 0.0, "fpr": round(fp / len(neg), 4)})
    at = lambda xs: round(sum(s >= cfg.threshold for s in xs) / len(xs), 4) if xs else None
    return {"config": cfg.__dict__, "n_programs": len(programs), "n_negative_pairs": len(neg),
            "recall_at_threshold": {k: at(v) for k, v in pos_scores.items()},
            "mean_score": {k: round(sum(v) / len(v), 4) for k, v in pos_scores.items() if v},
            "negative_mean_score": round(sum(neg) / len(neg), 4), "negative_fpr_at_threshold": at(neg), "sweep": sweep}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data"); ap.add_argument("--stdlib", action="store_true"); ap.add_argument("--n", type=int, default=120)
    ap.add_argument("--k", type=int, default=8); ap.add_argument("--w", type=int, default=5)
    ap.add_argument("--threshold", type=float, default=0.5); ap.add_argument("--out", default=str(ARTIFACTS / "plagiarism_metrics.json"))
    a = ap.parse_args()
    if a.stdlib:
        programs = stdlib_functions(a.n)
    elif a.data:
        seen, programs = set(), []
        for r in read_jsonl(a.data):
            if r["label"] == 0 and r.get("language") == "python" and r["group_id"] not in seen:
                seen.add(r["group_id"]); programs.append(r["code"])
        programs = programs[: a.n]
    else:
        raise SystemExit("pass --data or --stdlib")
    res = evaluate(programs, PlagiarismConfig(k=a.k, w=a.w, threshold=a.threshold))
    res["corpus"] = "python stdlib functions (sanity check)" if a.stdlib else a.data
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=2))
    print(json.dumps({k: res[k] for k in ("n_programs", "recall_at_threshold", "negative_mean_score", "negative_fpr_at_threshold")}, indent=2))


if __name__ == "__main__":
    main()
