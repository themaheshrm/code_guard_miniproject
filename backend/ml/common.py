"""Shared dataset I/O, leakage-free splitting and evaluation metrics."""
from __future__ import annotations

import json
import random
from pathlib import Path

import numpy as np
from sklearn.metrics import (average_precision_score, confusion_matrix, f1_score, precision_score,
                             recall_score, roc_auc_score, roc_curve)

ARTIFACTS = Path(__file__).resolve().parent / "artifacts"


def read_jsonl(path: str | Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path: str | Path, rows: list[dict]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def group_split(group_ids: list[str], seed: int = 42, ratios=(0.70, 0.15, 0.15)) -> dict[str, str]:
    """Assign whole groups (problems) to train/val/test so no problem appears in two splits."""
    uniq = sorted(set(group_ids))
    random.Random(seed).shuffle(uniq)
    n = len(uniq)
    n_tr = max(1, round(n * ratios[0])) if n >= 3 else n
    n_va = max(1, round(n * ratios[1])) if n >= 3 else 0
    out = {}
    for i, g in enumerate(uniq):
        out[g] = "train" if i < n_tr else "val" if i < n_tr + n_va else "test"
    return out


def assign_splits(rows: list[dict], seed: int = 42) -> list[dict]:
    """Respect an existing `split` field (e.g. Devign/Big-Vul official splits); otherwise split by group_id."""
    if rows and all("split" in r and r["split"] for r in rows):
        return rows
    mapping = group_split([str(r.get("group_id", r["id"])) for r in rows], seed)
    for r in rows:
        r["split"] = mapping[str(r.get("group_id", r["id"]))]
    return rows


def pick_threshold(y: np.ndarray, p: np.ndarray, max_fpr: float = 0.05) -> float:
    """Highest-recall threshold whose false-positive rate on `y` stays <= max_fpr (flagging honest authors is costly)."""
    if len(set(y.tolist())) < 2:
        return 0.5
    best, best_key = 0.5, (-1.0, -1.0)
    for t in np.unique(np.round(p, 4)):
        pred = p >= t
        neg = (y == 0).sum()
        fpr = ((pred) & (y == 0)).sum() / neg if neg else 0.0
        if fpr <= max_fpr:
            key = (recall_score(y, pred, zero_division=0), f1_score(y, pred, zero_division=0))
            if key > best_key:
                best, best_key = float(t), key
    return best


def report(y, p, threshold: float = 0.5) -> dict:
    y, p = np.asarray(y).astype(int), np.asarray(p, dtype=float)
    pred = (p >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    both = len(set(y.tolist())) == 2
    r = {
        "n": int(len(y)), "threshold": round(float(threshold), 4),
        "accuracy": round(float((pred == y).mean()), 4) if len(y) else None,
        "precision": round(float(precision_score(y, pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y, pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y, pred, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc_score(y, p)), 4) if both else None,
        "pr_auc": round(float(average_precision_score(y, p)), 4) if both else None,
        "false_positive_rate": round(float(fp / (fp + tn)), 4) if (fp + tn) else None,
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }
    if both:
        fpr, tpr, _ = roc_curve(y, p)
        idx = np.unique(np.linspace(0, len(fpr) - 1, min(60, len(fpr))).astype(int))
        r["roc_curve"] = [{"fpr": round(float(fpr[i]), 4), "tpr": round(float(tpr[i]), 4)} for i in idx]
    return r


def breakdowns(rows: list[dict], p: np.ndarray, threshold: float, lengths: list[int]) -> dict:
    """Per-length-bucket metrics and per-generator recall (the evaluation plan's breakdowns)."""
    y = np.array([r["label"] for r in rows])
    out: dict = {"by_length": [], "by_generator": []}
    for lo, hi, name in [(0, 15, "<15 lines"), (15, 40, "15-40 lines"), (40, 100, "40-100 lines"), (100, 10**9, ">100 lines")]:
        m = np.array([lo <= n < hi for n in lengths])
        if m.sum() >= 2:
            rep = report(y[m], p[m], threshold)
            out["by_length"].append({"bucket": name, "n": rep["n"], "accuracy": rep["accuracy"], "f1": rep["f1"],
                                     "recall": rep["recall"], "false_positive_rate": rep["false_positive_rate"]})
    for g in sorted({r.get("generator") or "" for r in rows if r["label"] == 1}):
        m = np.array([r["label"] == 1 and (r.get("generator") or "") == g for r in rows])
        if m.sum():
            out["by_generator"].append({"generator": g or "unknown", "n": int(m.sum()), "recall": round(float((p[m] >= threshold).mean()), 4)})
    return out
