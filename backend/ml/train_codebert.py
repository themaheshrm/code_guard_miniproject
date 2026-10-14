"""Stage 2: fine-tune CodeBERT / UniXcoder as a binary classifier.

    python -m ml.train_codebert --task ai   --data data/datasets/ai_dataset.jsonl
    python -m ml.train_codebert --task vuln --data data/datasets/vuln_dataset.jsonl   # stretch objective

Needs torch + transformers (requirements-ml.txt); a GPU (Colab/Kaggle) is strongly recommended.
Model selection uses ROC-AUC (ai) or PR-AUC (vuln, imbalanced) on the validation split.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from .common import ARTIFACTS, assign_splits, breakdowns, pick_threshold, read_jsonl, report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--task", choices=["ai", "vuln"], required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--model", default="microsoft/codebert-base", help="e.g. microsoft/unixcoder-base")
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--max-len", type=int, default=512)
    ap.add_argument("--max-fpr", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--languages", nargs="*")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    import torch
    from torch.utils.data import DataLoader, Dataset
    from transformers import AutoModelForSequenceClassification, AutoTokenizer, get_linear_schedule_with_warmup

    torch.manual_seed(a.seed)
    np.random.seed(a.seed)
    out = Path(a.out or ARTIFACTS / f"codebert_{a.task}")
    rows = read_jsonl(a.data)
    if a.languages:
        rows = [r for r in rows if r.get("language", "python") in a.languages]
    rows = assign_splits(rows, a.seed)
    part = {s: [r for r in rows if r["split"] == s] for s in ("train", "val", "test")}
    print({k: len(v) for k, v in part.items()})
    if not part["train"] or not part["val"]:
        raise SystemExit("Need non-empty train and val splits.")

    dev = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
    tok = AutoTokenizer.from_pretrained(a.model)
    model = AutoModelForSequenceClassification.from_pretrained(a.model, num_labels=2).to(dev)

    class DS(Dataset):
        def __init__(self, rs): self.rs = rs
        def __len__(self): return len(self.rs)
        def __getitem__(self, i): return self.rs[i]["code"], self.rs[i]["label"]

    def collate(batch):
        enc = tok([c for c, _ in batch], truncation=True, max_length=a.max_len, padding=True, return_tensors="pt")
        enc["labels"] = torch.tensor([l for _, l in batch])
        return enc

    def predict(rs) -> np.ndarray:
        model.eval()
        ps = []
        with torch.no_grad():
            for b in DataLoader(DS(rs), batch_size=a.batch_size * 2, collate_fn=collate):
                b = {k: v.to(dev) for k, v in b.items() if k != "labels"}
                ps.append(torch.softmax(model(**b).logits.float(), -1)[:, 1].cpu().numpy())
        return np.concatenate(ps)

    ytr = np.array([r["label"] for r in part["train"]])
    pos = max(1, int(ytr.sum()))
    weights = torch.tensor([1.0, (len(ytr) - pos) / pos if a.task == "vuln" else 1.0], device=dev)  # class-imbalance handling
    loss_fn = torch.nn.CrossEntropyLoss(weight=weights)
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=0.01)
    loader = DataLoader(DS(part["train"]), batch_size=a.batch_size, shuffle=True, collate_fn=collate)
    total = len(loader) * a.epochs
    sched = get_linear_schedule_with_warmup(opt, int(0.1 * total), total)
    amp = dev == "cuda"
    scaler = torch.cuda.amp.GradScaler(enabled=amp)
    yva = np.array([r["label"] for r in part["val"]])
    key = "pr_auc" if a.task == "vuln" else "roc_auc"
    best, history = -1.0, []

    for ep in range(a.epochs):
        model.train()
        run = 0.0
        for step, b in enumerate(loader, 1):
            b = {k: v.to(dev) for k, v in b.items()}
            labels = b.pop("labels")
            with torch.autocast(device_type="cuda", enabled=amp):
                loss = loss_fn(model(**b).logits.float(), labels)
            opt.zero_grad()
            scaler.scale(loss).backward()
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            scaler.step(opt)
            scaler.update()
            sched.step()
            run += loss.item()
        pv = predict(part["val"])
        rep = report(yva, pv, 0.5)
        history.append({"epoch": ep + 1, "train_loss": round(run / len(loader), 4), "val_" + key: rep[key], "val_f1": rep["f1"]})
        print(history[-1])
        score = rep[key] if rep[key] is not None else rep["f1"]
        if score > best:
            best = score
            out.mkdir(parents=True, exist_ok=True)
            model.save_pretrained(out)
            tok.save_pretrained(out)

    model = AutoModelForSequenceClassification.from_pretrained(out).to(dev)  # reload best checkpoint
    pv = predict(part["val"])
    thr = pick_threshold(yva, pv, a.max_fpr) if a.task == "ai" else float(max(
        np.unique(np.round(pv, 4)), key=lambda t: report(yva, pv, t)["f1"]))
    metrics = {"history": history, "model": a.model, "task": a.task, "split_sizes": {k: len(v) for k, v in part.items()}}
    if part["test"]:
        pt = predict(part["test"])
        yt = np.array([r["label"] for r in part["test"]])
        metrics["test"] = report(yt, pt, thr)
        metrics["test_at_0.5"] = report(yt, pt, 0.5)
        metrics.update(breakdowns(part["test"], pt, thr, [r["code"].count("\n") + 1 for r in part["test"]]))
        print("test", {k: v for k, v in metrics["test"].items() if k not in ("roc_curve", "confusion_matrix")})
    (out / "meta.json").write_text(json.dumps({"threshold": thr, "base_model": a.model, "task": a.task, "max_len": a.max_len,
                                               "trained_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "seed": a.seed}, indent=2))
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
