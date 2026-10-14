"""Stage 1 of the AI-code detector: stylometric features + XGBoost baseline.

    python -m ml.train_xgboost --data data/datasets/ai_dataset.jsonl [--languages python]
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter

import numpy as np
import xgboost as xgb

from app.core.features import FEATURE_NAMES, feature_vector

from .common import ARTIFACTS, assign_splits, breakdowns, pick_threshold, read_jsonl, report


def train(rows: list[dict], out_dir, seed: int = 42, max_fpr: float = 0.05, quiet: bool = False) -> dict:
    rows = assign_splits(rows, seed)
    X = np.array([feature_vector(r["code"], r.get("language", "python")) for r in rows])
    y = np.array([r["label"] for r in rows])
    split = np.array([r["split"] for r in rows])
    tr, va, te = (split == "train"), (split == "val"), (split == "test")
    if tr.sum() < 4 or len(set(y[tr].tolist())) < 2:
        raise SystemExit("Not enough labelled training data in both classes.")
    pos, neg = (y[tr] == 1).sum(), (y[tr] == 0).sum()
    params = dict(objective="binary:logistic", eval_metric="logloss", max_depth=5, eta=0.05, subsample=0.8,
                  colsample_bytree=0.8, min_child_weight=2, scale_pos_weight=float(neg / max(1, pos)), seed=seed)
    dtr = xgb.DMatrix(X[tr], y[tr], feature_names=FEATURE_NAMES)
    evals = [(dtr, "train")]
    use_val = va.sum() >= 4 and len(set(y[va].tolist())) == 2
    if use_val:
        dva = xgb.DMatrix(X[va], y[va], feature_names=FEATURE_NAMES)
        evals.append((dva, "val"))
    booster = xgb.train(params, dtr, num_boost_round=800, evals=evals, verbose_eval=False,
                        early_stopping_rounds=40 if use_val else None)

    def prob(mask):
        return booster.predict(xgb.DMatrix(X[mask], feature_names=FEATURE_NAMES))

    thr = pick_threshold(y[va], prob(va), max_fpr) if use_val else 0.5
    metrics = {"split_sizes": {k: int(v.sum()) for k, v in (("train", tr), ("val", va), ("test", te))},
               "class_balance": dict(Counter(map(int, y))), "threshold_policy": f"max recall with val FPR <= {max_fpr}"}
    if te.sum():
        p_te = prob(te)
        metrics["test"] = report(y[te], p_te, thr)
        metrics["test_at_0.5"] = report(y[te], p_te, 0.5)
        te_rows = [r for r, m in zip(rows, te) if m]
        metrics.update(breakdowns(te_rows, p_te, thr, [r["code"].count("\n") + 1 for r in te_rows]))
    if use_val:
        metrics["val"] = report(y[va], prob(va), thr)
    gain = booster.get_score(importance_type="gain")
    metrics["feature_importance"] = sorted(({"feature": k, "gain": round(v, 4)} for k, v in gain.items()), key=lambda x: -x["gain"])

    out_dir.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(out_dir / "xgb_ai.json"))
    meta = {"feature_names": FEATURE_NAMES, "threshold": thr, "trained_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "languages": sorted({r.get("language", "python") for r in rows}), "seed": seed, "best_iteration": getattr(booster, "best_iteration", None)}
    (out_dir / "xgb_ai_meta.json").write_text(json.dumps(meta, indent=2))
    (out_dir / "xgb_ai_metrics.json").write_text(json.dumps(metrics, indent=2))
    if not quiet and "test" in metrics:
        t = metrics["test"]
        print(f"test  acc={t['accuracy']} P={t['precision']} R={t['recall']} F1={t['f1']} AUC={t['roc_auc']} FPR={t['false_positive_rate']}")
    return metrics


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", required=True)
    ap.add_argument("--languages", nargs="*", help="restrict training to these languages")
    ap.add_argument("--max-fpr", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=str(ARTIFACTS))
    a = ap.parse_args()
    from pathlib import Path

    rows = read_jsonl(a.data)
    if a.languages:
        rows = [r for r in rows if r.get("language", "python") in a.languages]
    train(rows, Path(a.out), a.seed, a.max_fpr)


if __name__ == "__main__":
    main()
