"""AI-generated-code detector: XGBoost (stylometric features) + fine-tuned CodeBERT, with block attribution."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import numpy as np

from ..core.features import FEATURE_NAMES, feature_vector
from ..core.parsing import build_ast, functions


class XGBDetector:
    def __init__(self, artifacts: Path):
        self.available = False
        self.meta: dict = {}
        self.error: str | None = None
        model_path, meta_path = artifacts / "xgb_ai.json", artifacts / "xgb_ai_meta.json"
        if not (model_path.exists() and meta_path.exists()):
            self.error = "No trained XGBoost model. Run: python -m ml.train_xgboost --data <dataset.jsonl>"
            return
        import xgboost as xgb

        self._xgb = xgb
        self.booster = xgb.Booster()
        self.booster.load_model(str(model_path))
        self.meta = json.loads(meta_path.read_text())
        if self.meta.get("feature_names") != FEATURE_NAMES:
            self.error = "Model was trained with a different feature set; retrain."
            return
        self.threshold = float(self.meta.get("threshold", 0.5))
        self.available = True

    def proba(self, code: str, lang: str) -> float:
        d = self._xgb.DMatrix(np.array([feature_vector(code, lang)]), feature_names=FEATURE_NAMES)
        return float(self.booster.predict(d)[0])

    def explain(self, code: str, lang: str, top: int = 8) -> list[dict]:
        d = self._xgb.DMatrix(np.array([feature_vector(code, lang)]), feature_names=FEATURE_NAMES)
        contrib = self.booster.predict(d, pred_contribs=True)[0][:-1]
        vec = feature_vector(code, lang)
        order = np.argsort(-np.abs(contrib))[:top]
        return [{"feature": FEATURE_NAMES[i], "value": round(vec[i], 4), "contribution": round(float(contrib[i]), 4),
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
            self.error = "No fine-tuned CodeBERT model. Run: python -m ml.train_codebert --task ai ..."
            return
        self.meta = json.loads((directory / "meta.json").read_text())
        try:
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
        dev = next(self._model.parameters()).device if self._model else "cpu"
        for w in windows[:12]:
            inp = torch.tensor([[self._tok.cls_token_id] + w + [self._tok.sep_token_id]], device=dev)
            with torch.no_grad():
                probs.append(float(torch.softmax(self._model(input_ids=inp).logits, -1)[0, 1]))
        return float(np.mean(probs))


def occlusion_blocks(code: str, lang: str, predict: Callable[[str], float], base: float, max_blocks: int = 12) -> list[dict]:
    """Block-level attribution: probability drop when a function/class is removed from the file.

    Positive contribution => the block pushes the verdict toward 'AI-generated'.
    """
    root = build_ast(code, lang)
    blocks = [(f.start, f.end, f.name or "<function>") for f in functions(root)]
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
    def __init__(self, artifacts: Path, w_xgb: float, w_bert: float, enable_codebert: bool = True):
        self.xgb = XGBDetector(artifacts)
        self.bert = CodeBERTDetector(artifacts / "codebert_ai", enable_codebert)
        self.w_xgb, self.w_bert = w_xgb, w_bert

    def status(self) -> dict:
        return {"xgboost": {"available": self.xgb.available, "error": self.xgb.error, "threshold": getattr(self.xgb, "threshold", None)},
                "codebert": {"available": self.bert.available, "error": self.bert.error, "threshold": getattr(self.bert, "threshold", None)}}

    def predict(self, code: str, lang: str, explain: bool = True) -> dict:
        if not (self.xgb.available or self.bert.available):
            return {"status": "model_unavailable", "probability": None, "label": None, "models": {},
                    "message": self.xgb.error or self.bert.error}
        models: dict[str, dict] = {}
        parts: list[tuple[float, float, float]] = []  # (prob, weight, threshold)
        if self.xgb.available:
            p = self.xgb.proba(code, lang)
            models["xgboost"] = {"probability": round(p, 4), "threshold": self.xgb.threshold}
            parts.append((p, self.w_xgb, self.xgb.threshold))
        if self.bert.available:
            p = self.bert.proba(code, lang)
            models["codebert"] = {"probability": round(p, 4), "threshold": self.bert.threshold}
            parts.append((p, self.w_bert, self.bert.threshold))
        wsum = sum(w for _, w, _ in parts)
        prob = sum(p * w for p, w, _ in parts) / wsum
        thr = sum(t * w for _, w, t in parts) / wsum
        result = {"status": "ok", "probability": round(prob, 4), "threshold": round(thr, 4), "label": "ai" if prob >= thr else "human",
                  "models": models, "top_features": [], "blocks": []}
        if explain:
            if self.xgb.available:
                result["top_features"] = self.xgb.explain(code, lang)
            # Attribution uses the cheaper feature model when present, so large files stay responsive.
            fn = self.xgb.proba if self.xgb.available else self.bert.proba
            base = fn(code, lang) if self.xgb.available else prob
            result["blocks"] = occlusion_blocks(code, lang, lambda c: fn(c, lang), base)
        return result
