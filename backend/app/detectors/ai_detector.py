"""AI-generated-code detector.

Three engines, combined as a weighted ensemble:

* **XGBoost** on 45 stylometric features (``ml/train_xgboost.py``) — trained model, optional.
* **CodeBERT** fine-tuned classifier (``ml/train_codebert.py``) — trained model, optional (needs torch).
* **Heuristic stylometry** — a transparent, always-available scorer built from well-documented signals of
  LLM-written code (dense docstrings/comments, type hints, long descriptive identifiers, perfectly uniform
  formatting, main guards, defensive error handling). It needs no training data, so the app gives a useful,
  explainable estimate out of the box; when trained models are present it only gets a small ensemble weight.

Every response says which engines produced the score. Block-level attribution uses occlusion: the probability drop
when a function/class is removed from the file.
"""
from __future__ import annotations

import json
import math
import threading
from pathlib import Path
from typing import Callable

import numpy as np

from ..core.features import FEATURE_NAMES, extract_features, feature_vector
from ..core.parsing import build_ast, functions, lex

MAX_EXPLAIN_CHARS = 80_000  # occlusion re-scores the file once per block; skip it for huge inputs


class XGBDetector:
    def __init__(self, artifacts: Path):
        self.available = False
        self.meta: dict = {}
        self.error: str | None = None
        model_path, meta_path = artifacts / "xgb_ai.json", artifacts / "xgb_ai_meta.json"
        if not (model_path.exists() and meta_path.exists()):
            self.error = "No trained XGBoost model yet. Train one from the Evaluation page or: python -m ml.train_xgboost --data <dataset.jsonl>"
            return
        try:
            import xgboost as xgb

            self._xgb = xgb
            self.booster = xgb.Booster()
            self.booster.load_model(str(model_path))
            self.meta = json.loads(meta_path.read_text())
        except Exception as e:  # corrupt artefact must not take the API down
            self.error = f"XGBoost model could not be loaded: {e}"
            return
        if self.meta.get("feature_names") != FEATURE_NAMES:
            self.error = "Model was trained with a different feature set; retrain."
            return
        self.threshold = float(self.meta.get("threshold", 0.5))
        self.available = True

    def proba(self, code: str, lang: str) -> float:
        d = self._xgb.DMatrix(np.array([feature_vector(code, lang)]), feature_names=FEATURE_NAMES)
        return float(self.booster.predict(d)[0])

    def explain(self, code: str, lang: str, top: int = 8) -> list[dict]:
        vec = feature_vector(code, lang)
        d = self._xgb.DMatrix(np.array([vec]), feature_names=FEATURE_NAMES)
        contrib = self.booster.predict(d, pred_contribs=True)[0][:-1]
        order = np.argsort(-np.abs(contrib))[:top]
        return [{"feature": FEATURE_NAMES[i], "label": FEATURE_LABELS.get(FEATURE_NAMES[i], FEATURE_NAMES[i]),
                 "value": round(vec[i], 4), "contribution": round(float(contrib[i]), 4),
                 "direction": "ai" if contrib[i] > 0 else "human"} for i in order]


class CodeBERTDetector:
    def __init__(self, directory: Path, enabled: bool = True):
        self.available = False
        self.meta: dict = {}
        self.error: str | None = None
        if not enabled:
            self.error = "CodeBERT detector disabled by configuration."
            return
        if not ((directory / "config.json").exists() and (directory / "meta.json").exists()):
            self.error = "No fine-tuned CodeBERT model (optional, needs a GPU to train): python -m ml.train_codebert --task ai ..."
            return
        try:
            self.meta = json.loads((directory / "meta.json").read_text())
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            self._torch = torch
            self._tok = AutoTokenizer.from_pretrained(directory)
            self._model = AutoModelForSequenceClassification.from_pretrained(directory).eval()
            self.threshold = float(self.meta.get("threshold", 0.5))
            self.available = True
        except Exception as e:
            self.error = f"CodeBERT could not be loaded: {e}"

    def proba(self, code: str, lang: str = "") -> float:
        """Average over 512-token windows (stride 256) so long files are fully covered."""
        torch = self._torch
        ids = self._tok(code, add_special_tokens=False, truncation=False)["input_ids"]
        size, stride = 510, 256
        windows = [ids[i:i + size] for i in range(0, max(1, len(ids) - size + stride), stride)] or [ids]
        probs = []
        dev = next(self._model.parameters()).device
        for w in windows[:12]:
            inp = torch.tensor([[self._tok.cls_token_id] + w + [self._tok.sep_token_id]], device=dev)
            with torch.no_grad():
                probs.append(float(torch.softmax(self._model(input_ids=inp).logits, -1)[0, 1]))
        return float(np.mean(probs))


# ------------------------------------------------------------------------------------------- heuristic
FEATURE_LABELS = {
    "comment_line_ratio": "Comment density", "docstring_ratio": "Docstring coverage", "type_hint_ratio": "Type-hint coverage",
    "id_avg_len": "Identifier length", "id_single_char_ratio": "Single-letter names", "trailing_ws_ratio": "Trailing whitespace",
    "comma_space_ratio": "Spacing after commas", "blank_line_ratio": "Blank-line rhythm", "main_guard": "Main guard / entry point",
    "magic_number_ratio": "Magic numbers", "id_long_ratio": "Very descriptive names", "try_per_function": "Defensive error handling",
    "indent_consistency": "Indentation uniformity", "documented_functions": "Documented functions", "naming_consistency": "Naming-style consistency",
    "line_len_cv": "Line-length variation", "print_per_line": "Debug prints",
}


def _clip(x: float, lo: float = -1.5, hi: float = 1.5) -> float:
    return max(lo, min(hi, x))


def _documented_functions(code: str, lang: str) -> float:
    """Share of functions with a comment/docstring directly above or at the top of the body (all languages)."""
    fns = functions(build_ast(code, lang))
    if not fns:
        return 0.0
    comment_lines: set[int] = set()
    for t in lex(code, lang):
        if t.kind == "comment" or (t.kind == "str" and t.text.startswith(('"""', "'''"))):
            comment_lines.update(range(t.line, t.line + t.text.count("\n") + 1))
    hit = sum(1 for f in fns if {f.start - 1, f.start, f.start + 1} & comment_lines)
    return hit / len(fns)


def _naming_consistency(code: str, lang: str) -> float:
    import re

    ids = {t.text for t in lex(code, lang) if t.kind == "id" and len(t.text) > 2}
    snake = sum(bool(re.match(r"^[a-z][a-z0-9]*(_[a-z0-9]+)+$", i)) for i in ids)
    camel = sum(bool(re.match(r"^[a-z]+([A-Z][a-z0-9]*)+$", i)) for i in ids)
    styled = snake + camel
    return max(snake, camel) / styled if styled >= 3 else 1.0


class HeuristicDetector:
    """Logistic combination of interpretable stylometric signals. Always available; no training data required."""

    name = "heuristic"
    # Polished, heavily documented human code (e.g. library code) also scores high, so the bar is set above 0.5.
    threshold = 0.6
    available = True
    error = None
    BIAS = -0.8

    # (feature, centre, scale, weight, languages or None). contribution = weight * clip((value - centre) / scale)
    SIGNALS: list[tuple[str, float, float, float, tuple[str, ...] | None]] = [
        ("comment_line_ratio", 0.08, 0.08, 0.75, None),
        ("documented_functions", 0.35, 0.35, 0.85, None),
        ("docstring_ratio", 0.30, 0.35, 0.55, ("python",)),
        ("type_hint_ratio", 0.30, 0.35, 0.80, ("python",)),
        ("id_avg_len", 5.5, 2.0, 0.85, None),
        ("id_single_char_ratio", 0.22, -0.15, 0.70, None),
        ("id_long_ratio", 0.06, 0.08, 0.35, None),
        ("trailing_ws_ratio", 0.02, -0.04, 0.45, None),
        ("comma_space_ratio", 0.85, 0.12, 0.45, None),
        ("blank_line_ratio", 0.10, 0.06, 0.35, None),
        ("naming_consistency", 0.85, 0.12, 0.30, None),
        ("main_guard", 0.5, 0.5, 0.35, ("python",)),
        ("try_per_function", 0.10, 0.30, 0.25, ("python",)),
        ("magic_number_ratio", 0.03, -0.03, 0.25, None),
        ("print_per_line", 0.06, -0.06, 0.20, None),
    ]

    def _signals(self, code: str, lang: str) -> tuple[float, list[dict], float]:
        f = extract_features(code, lang)
        f["documented_functions"] = _documented_functions(code, lang)
        f["naming_consistency"] = _naming_consistency(code, lang)
        nonblank = sum(1 for ln in code.splitlines() if ln.strip())
        # Short snippets carry little stylistic evidence: shrink the logit toward 0 (probability toward 0.5).
        evidence = min(1.0, max(0.25, nonblank / 30))
        parts = []
        for feat, centre, scale, weight, langs in self.SIGNALS:
            if langs and lang not in langs:
                continue
            c = weight * _clip((f[feat] - centre) / scale)
            parts.append({"feature": feat, "label": FEATURE_LABELS.get(feat, feat), "value": round(f[feat], 4),
                          "contribution": round(c * evidence, 4), "direction": "ai" if c > 0 else "human"})
        raw = sum(p["contribution"] for p in parts) / evidence
        logit = (self.BIAS + raw) * evidence
        return 1 / (1 + math.exp(-logit)), parts, evidence

    def proba(self, code: str, lang: str) -> float:
        return self._signals(code, lang)[0]

    def explain(self, code: str, lang: str, top: int = 8) -> list[dict]:
        parts = self._signals(code, lang)[1]
        return sorted(parts, key=lambda p: -abs(p["contribution"]))[:top]

    def evidence(self, code: str, lang: str) -> float:
        return self._signals(code, lang)[2]


def occlusion_blocks(code: str, lang: str, predict: Callable[[str], float], base: float, max_blocks: int = 12) -> list[dict]:
    """Block-level attribution: probability drop when a function/class is removed from the file.

    Positive contribution => the block pushes the verdict toward 'AI-generated'.
    """
    root = build_ast(code, lang)
    fns = functions(root)
    # keep only outermost functions so nested helpers are not double counted
    outer = [f for f in fns if not any(o is not f and o.start <= f.start and f.end <= o.end for o in fns)]
    blocks = [(f.start, f.end, f.name or "<function>") for f in outer]
    lines = code.splitlines()
    if not blocks:  # no functions: fall back to fixed windows of lines
        step = max(8, len(lines) // 6 or 8)
        blocks = [(i + 1, min(i + step, len(lines)), f"lines {i + 1}-{min(i + step, len(lines))}") for i in range(0, len(lines), step)]
    blocks = [b for b in blocks if b[1] - b[0] >= 2][:max_blocks]
    out = []
    for s, e, name in blocks:
        rest = "\n".join(lines[:s - 1] + lines[e:])
        if len(rest.strip()) < 20:
            continue
        try:
            out.append({"start": s, "end": e, "name": name, "contribution": round(base - predict(rest), 4)})
        except Exception:
            continue
    return sorted(out, key=lambda x: -abs(x["contribution"]))


class AIDetector:
    def __init__(self, artifacts: Path, w_xgb: float, w_bert: float, enable_codebert: bool = True,
                 enable_heuristic: bool = True, w_heuristic: float = 0.2):
        self.artifacts, self.enable_codebert, self.enable_heuristic = artifacts, enable_codebert, enable_heuristic
        self.w_xgb, self.w_bert, self.w_heur = w_xgb, w_bert, w_heuristic
        self._lock = threading.Lock()
        self.heur = HeuristicDetector() if enable_heuristic else None
        self._load()

    def _load(self) -> None:
        xgb_det = XGBDetector(self.artifacts)
        bert = CodeBERTDetector(self.artifacts / "codebert_ai", self.enable_codebert)
        with self._lock:
            self.xgb, self.bert = xgb_det, bert

    def reload(self) -> dict:
        """Re-read model artefacts (e.g. after training from the UI) without restarting the server."""
        self._load()
        return self.status()

    @property
    def trained_available(self) -> bool:
        return self.xgb.available or self.bert.available

    def status(self) -> dict:
        return {
            "xgboost": {"available": self.xgb.available, "error": self.xgb.error, "threshold": getattr(self.xgb, "threshold", None),
                        "trained_at": self.xgb.meta.get("trained_at")},
            "codebert": {"available": self.bert.available, "error": self.bert.error, "threshold": getattr(self.bert, "threshold", None)},
            "heuristic": {"available": self.heur is not None, "error": None if self.heur else "Heuristic engine disabled by configuration.",
                          "threshold": HeuristicDetector.threshold},
        }

    def predict(self, code: str, lang: str, explain: bool = True) -> dict:
        xgb_det, bert, heur = self.xgb, self.bert, self.heur
        if not (xgb_det.available or bert.available or heur):
            return {"status": "model_unavailable", "probability": None, "label": None, "models": {},
                    "message": xgb_det.error or bert.error}
        models: dict[str, dict] = {}
        parts: list[tuple[float, float, float]] = []  # (prob, weight, threshold)
        trained = xgb_det.available or bert.available
        if xgb_det.available:
            p = xgb_det.proba(code, lang)
            models["xgboost"] = {"probability": round(p, 4), "threshold": xgb_det.threshold}
            parts.append((p, self.w_xgb, xgb_det.threshold))
        if bert.available:
            p = bert.proba(code, lang)
            models["codebert"] = {"probability": round(p, 4), "threshold": bert.threshold}
            parts.append((p, self.w_bert, bert.threshold))
        evidence = 1.0
        if heur:
            p = heur.proba(code, lang)
            evidence = heur.evidence(code, lang)
            models["heuristic"] = {"probability": round(p, 4), "threshold": heur.threshold}
            parts.append((p, self.w_heur if trained else 1.0, heur.threshold))
        wsum = sum(w for _, w, _ in parts) or 1.0
        prob = sum(p * w for p, w, _ in parts) / wsum
        thr = sum(t * w for _, w, t in parts) / wsum
        margin = abs(prob - thr)
        confidence = "high" if margin >= 0.3 and evidence >= 0.8 else "medium" if margin >= 0.15 and evidence >= 0.5 else "low"
        engine = "ensemble" if len(parts) > 1 else next(iter(models))
        result = {"status": "ok", "probability": round(prob, 4), "threshold": round(thr, 4), "label": "ai" if prob >= thr else "human",
                  "confidence": confidence, "engine": engine, "models": models, "top_features": [], "blocks": [],
                  "message": "" if trained else "Heuristic stylometry only (no trained model loaded). Train XGBoost for a data-driven score."}
        if explain:
            explainer = xgb_det if xgb_det.available else heur
            if explainer is not None:
                result["top_features"] = explainer.explain(code, lang)
            if len(code) <= MAX_EXPLAIN_CHARS:
                # Attribution uses the cheapest available engine so large files stay responsive.
                fn = xgb_det.proba if xgb_det.available else heur.proba if heur else bert.proba
                result["blocks"] = occlusion_blocks(code, lang, lambda c: fn(c, lang), fn(code, lang))
        return result
