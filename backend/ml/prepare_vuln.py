"""Convert Devign / Big-Vul into the shared JSONL schema for `train_codebert --task vuln`.

    python -m ml.prepare_vuln --dataset devign  --out data/datasets/vuln_dataset.jsonl
    python -m ml.prepare_vuln --dataset bigvul  --out data/datasets/vuln_dataset.jsonl --max-rows 60000

Devign comes from CodeXGLUE (`google/code_x_glue_cc_defect_detection`, official train/validation/test splits).
Big-Vul is read from the Hugging Face hub; column names differ between mirrors, so override --code-col/--label-col/--cwe-col
if the defaults do not match your copy. Check each dataset's licence/terms before redistributing derived files.
Class imbalance is kept as-is in the data; train_codebert applies class weights and reports PR-AUC / recall.
"""
from __future__ import annotations

import argparse
import hashlib

from .common import write_jsonl

PRESETS = {
    "devign": dict(hf="google/code_x_glue_cc_defect_detection", code="func", label="target", cwe=None, group="project"),
    "bigvul": dict(hf="bstee615/bigvul", code="func_before", label="vul", cwe="CWE ID", group="project"),
}
SPLIT_MAP = {"train": "train", "validation": "val", "val": "val", "test": "test"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", choices=PRESETS, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-rows", type=int, default=0, help="0 = all")
    ap.add_argument("--hf-name"); ap.add_argument("--code-col"); ap.add_argument("--label-col"); ap.add_argument("--cwe-col")
    a = ap.parse_args()
    from datasets import load_dataset

    cfg = dict(PRESETS[a.dataset])
    code_col, label_col, cwe_col = a.code_col or cfg["code"], a.label_col or cfg["label"], a.cwe_col or cfg["cwe"]
    ds = load_dataset(a.hf_name or cfg["hf"])
    rows = []
    for split_name, part in ds.items():
        split = SPLIT_MAP.get(split_name)
        if split is None:
            continue
        for i, ex in enumerate(part):
            code = ex[code_col]
            if not code or len(code) < 20:
                continue
            rows.append({"id": hashlib.sha1(f"{a.dataset}{split}{i}".encode()).hexdigest()[:16], "group_id": str(ex.get(cfg["group"], i)),
                         "label": int(bool(ex[label_col])), "language": "c", "code": code, "source": a.dataset, "split": split,
                         **({"cwe": ex.get(cwe_col)} if cwe_col else {})})
            if a.max_rows and len(rows) >= a.max_rows:
                break
    write_jsonl(a.out, rows)
    pos = sum(r["label"] for r in rows)
    print(f"{len(rows)} functions, {pos} vulnerable ({100 * pos / max(1, len(rows)):.1f}%) -> {a.out}")


if __name__ == "__main__":
    main()
