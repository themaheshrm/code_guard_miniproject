import json

import numpy as np

from app.detectors.ai_detector import AIDetector
from ml.build_dataset import extract_code, merge
from ml.common import group_split, pick_threshold, read_jsonl, report, write_jsonl
from ml.train_xgboost import train


def test_group_split_has_no_leakage_and_roughly_70_15_15():
    groups = [f"p{i}" for i in range(100)] * 2
    m = group_split(groups)
    counts = {s: sum(v == s for v in m.values()) for s in ("train", "val", "test")}
    assert counts == {"train": 70, "val": 15, "test": 15}
    assert group_split(groups) == m  # deterministic


def test_report_metrics_known_values():
    r = report([0, 0, 1, 1], [0.1, 0.6, 0.4, 0.9], 0.5)
    assert r["confusion_matrix"] == {"tn": 1, "fp": 1, "fn": 1, "tp": 1}
    assert r["accuracy"] == 0.5 and r["false_positive_rate"] == 0.5 and r["roc_auc"] == 0.75


def test_threshold_respects_fpr_cap():
    y = np.array([0] * 100 + [1] * 100)
    p = np.concatenate([np.linspace(0, 0.8, 100), np.linspace(0.3, 1.0, 100)])
    thr = pick_threshold(y, p, 0.05)
    assert report(y, p, thr)["false_positive_rate"] <= 0.05


def test_xgboost_training_and_inference_roundtrip(pair_rows, tmp_path):
    # Mechanics only: synthetic stylistic data proves split/train/save/load/serve work, NOT real-world accuracy.
    metrics = train(pair_rows, tmp_path, quiet=True)
    assert metrics["test"]["roc_auc"] > 0.9 and metrics["feature_importance"] and metrics["by_length"]
    assert json.loads((tmp_path / "xgb_ai_meta.json").read_text())["threshold"] > 0
    det = AIDetector(tmp_path, 0.4, 0.6, enable_codebert=False)
    assert det.status()["xgboost"]["available"] and not det.status()["codebert"]["available"]
    from tests.conftest import synthetic_pair

    h, a = synthetic_pair(500)
    ph, pa = det.predict(h, "python"), det.predict(a, "python")
    assert pa["probability"] > ph["probability"] and pa["label"] == "ai" and ph["label"] == "human"
    assert pa["top_features"] and pa["blocks"]


def test_detector_reports_unavailable_without_models(tmp_path):
    r = AIDetector(tmp_path, 0.4, 0.6).predict("x = 1\n" * 10, "python")
    assert r["status"] == "model_unavailable" and r["probability"] is None


def test_dataset_merge_keeps_only_matched_valid_problems(tmp_path):
    good = "def solve(n):\n    return sum(range(n))\n\nprint(solve(10))\n"
    human = [{"id": "h1", "group_id": "p1", "label": 0, "language": "python", "code": good, "statement": "s"},
             {"id": "h2", "group_id": "p2", "label": 0, "language": "python", "code": good + "# x\n", "statement": "s"}]
    ai = [{"id": "a1", "group_id": "p1", "label": 1, "language": "python", "code": good.replace("solve", "total_for"), "generator": "m"},
          {"id": "a2", "group_id": "p3", "label": 1, "language": "python", "code": "def broken(:\n   pass  # padding padding padding", "generator": "m"}]
    write_jsonl(tmp_path / "h.jsonl", human)
    write_jsonl(tmp_path / "a.jsonl", ai)

    class A: pass
    a = A(); a.human, a.ai, a.out = str(tmp_path / "h.jsonl"), [str(tmp_path / "a.jsonl")], str(tmp_path / "o.jsonl")
    merge(a)
    out = read_jsonl(a.out)
    assert {r["group_id"] for r in out} == {"p1"} and {r["label"] for r in out} == {0, 1}


def test_extract_code_prefers_largest_fenced_block():
    assert extract_code("text\n```python\nx=1\n```\nmore\n```python\ny = 2\nz = 3\n```") == "y = 2\nz = 3"
    assert extract_code("print(1)") == "print(1)"
