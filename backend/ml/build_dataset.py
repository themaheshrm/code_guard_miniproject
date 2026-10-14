"""Build the labelled human-vs-AI dataset: SAME problem statements, human and LLM solutions.

Schema (one JSON object per line): id, group_id (= problem id, used for leakage-free splits), label (0 human / 1 AI),
language, code, source, generator, temperature, prompt_style.

    # 1) human solutions + problem statements
    python -m ml.build_dataset human-contests --out data/datasets/human.jsonl --max-problems 300 --per-problem 3
    python -m ml.build_dataset human-folder   --root my_problems/ --out data/datasets/human.jsonl
    python -m ml.build_dataset human-jsonl    --problems problems.jsonl --out data/datasets/human.jsonl
    # 2) LLM solutions for the same statements (varied prompts x temperatures)
    python -m ml.build_dataset generate --human data/datasets/human.jsonl --provider anthropic --model <model-id> \
           --out data/datasets/ai.jsonl
    # 3) merge, validate, dedupe, report
    python -m ml.build_dataset merge --human data/datasets/human.jsonl --ai data/datasets/ai.jsonl --out data/datasets/ai_dataset.jsonl

LICENCES: check and record the licence/terms of every source (CodeContests: CC BY 4.0; verify per release) and of the
LLM provider's output terms before publishing the dataset. Human code from before 2022 minimises LLM contamination.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

from .common import read_jsonl, write_jsonl

PROMPT_STYLES = {
    "plain": "Solve the following programming problem in {lang}. Return only a complete program in one code block.\n\n{statement}",
    "student": "You are a university student solving this assignment in {lang}. Write a correct, complete solution the way a typical student would. Return only the code in one code block.\n\n{statement}",
    "clean": "Write a clean, well-structured, well-commented {lang} solution to this problem, as in a code review. Return only the code in one code block.\n\n{statement}",
}
TEMPERATURES = [0.2, 0.7, 1.0]
_FENCE = re.compile(r"```[a-zA-Z0-9+#]*\n(.*?)```", re.S)
_LANG_NAMES = {"python": "Python 3", "java": "Java", "cpp": "C++", "c": "C", "javascript": "JavaScript"}


def _id(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


def extract_code(text: str) -> str:
    blocks = _FENCE.findall(text)
    return max(blocks, key=len).strip("\n") if blocks else text.strip()


def valid_python(code: str) -> bool:
    try:
        ast.parse(code)
        return len(code.strip()) > 0
    except SyntaxError:
        return False


# ------------------------------------------------------------------ human sources
def human_contests(a) -> None:
    from datasets import load_dataset  # HF `deepmind/code_contests`; solutions language ids: 3 = Python 3

    ds = load_dataset("deepmind/code_contests", split=a.split, streaming=True)
    rows, seen = [], 0
    for ex in ds:
        sols = [s for lang, s in zip(ex["solutions"]["language"], ex["solutions"]["solution"]) if lang == 3 and 80 <= len(s) <= 6000]
        if not sols or not ex["description"]:
            continue
        pid = _id(ex["name"])
        for k, s in enumerate(sols[: a.per_problem]):
            rows.append({"id": _id(pid, "h", str(k)), "group_id": pid, "label": 0, "language": "python", "code": s,
                         "source": "deepmind/code_contests", "statement": ex["description"][:6000], "generator": "human"})
        seen += 1
        if seen >= a.max_problems:
            break
    write_jsonl(a.out, rows)
    print(f"{seen} problems, {len(rows)} human solutions -> {a.out}")


def human_folder(a) -> None:
    """Layout: root/<problem>/statement.txt and root/<problem>/solutions/*.{py,java,c,cpp,js}"""
    ext = {".py": "python", ".java": "java", ".c": "c", ".cpp": "cpp", ".js": "javascript"}
    rows = []
    for pdir in sorted(Path(a.root).iterdir()):
        stmt = pdir / "statement.txt"
        if not (pdir.is_dir() and stmt.exists()):
            continue
        for f in sorted((pdir / "solutions").glob("*")):
            if f.suffix in ext:
                rows.append({"id": _id(pdir.name, f.name), "group_id": pdir.name, "label": 0, "language": ext[f.suffix],
                             "code": f.read_text(errors="ignore"), "source": str(a.root), "statement": stmt.read_text(), "generator": "human"})
    write_jsonl(a.out, rows)
    print(f"{len({r['group_id'] for r in rows})} problems, {len(rows)} solutions -> {a.out}")


def human_jsonl(a) -> None:
    """Input rows: {problem_id, statement, language, code, source?}. Use for CodeSearchNet (docstring = statement)."""
    rows = [{"id": _id(r["problem_id"], r["code"]), "group_id": str(r["problem_id"]), "label": 0, "language": r.get("language", "python"),
             "code": r["code"], "source": r.get("source", a.problems), "statement": r["statement"], "generator": "human"}
            for r in read_jsonl(a.problems)]
    write_jsonl(a.out, rows)
    print(f"{len(rows)} rows -> {a.out}")


# ------------------------------------------------------------------ LLM generation
def _make_caller(provider: str, model: str):
    if provider == "anthropic":
        import anthropic

        client = anthropic.Anthropic()

        def call(prompt: str, temperature: float) -> str:
            r = client.messages.create(model=model, max_tokens=2000, temperature=min(temperature, 1.0),
                                       messages=[{"role": "user", "content": prompt}])
            return "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
    elif provider == "openai":
        from openai import OpenAI

        client = OpenAI(base_url=os.getenv("OPENAI_BASE_URL") or None)

        def call(prompt: str, temperature: float) -> str:
            r = client.chat.completions.create(model=model, temperature=temperature, max_tokens=2000,
                                               messages=[{"role": "user", "content": prompt}])
            return r.choices[0].message.content or ""
    else:
        raise SystemExit(f"unknown provider {provider}")
    return call


def generate(a) -> None:
    call = _make_caller(a.provider, a.model)
    problems: dict[str, dict] = {}
    for r in read_jsonl(a.human):
        problems.setdefault(r["group_id"], r)
    done = {r["id"] for r in read_jsonl(a.out)} if Path(a.out).exists() else set()
    n_new = 0
    for pid, p in list(problems.items())[: a.max_problems]:
        for style, tmpl in PROMPT_STYLES.items():
            for temp in TEMPERATURES:
                for rep in range(a.samples):
                    rid = _id(pid, a.model, style, str(temp), str(rep))
                    if rid in done:
                        continue
                    prompt = tmpl.format(lang=_LANG_NAMES.get(p["language"], p["language"]), statement=p["statement"])
                    try:
                        code = extract_code(call(prompt, temp))
                    except Exception as e:
                        print(f"[warn] {pid} {style} {temp}: {e}", file=sys.stderr)
                        time.sleep(2)
                        continue
                    if p["language"] == "python" and not valid_python(code):
                        continue
                    row = {"id": rid, "group_id": pid, "label": 1, "language": p["language"], "code": code, "source": a.provider,
                           "generator": a.model, "temperature": temp, "prompt_style": style}
                    with open(a.out, "a", encoding="utf-8") as f:
                        f.write(__import__("json").dumps(row, ensure_ascii=False) + "\n")
                    n_new += 1
                    time.sleep(a.sleep)
    print(f"generated {n_new} new samples -> {a.out}")


# ------------------------------------------------------------------ merge / validate
def merge(a) -> None:
    rows, seen = [], set()
    for path in [a.human, *a.ai]:
        for r in read_jsonl(path):
            r.pop("statement", None)  # statements are not needed downstream; keeps the dataset small
            sha = hashlib.sha256(re.sub(r"\s+", "", r["code"]).encode()).hexdigest()
            if sha in seen or len(r["code"].strip()) < 40:
                continue
            if r["language"] == "python" and not valid_python(r["code"]):
                continue
            seen.add(sha)
            rows.append(r)
    # keep only problems that have BOTH classes, so every group is a matched comparison
    by_group: dict[str, set[int]] = {}
    for r in rows:
        by_group.setdefault(r["group_id"], set()).add(r["label"])
    rows = [r for r in rows if len(by_group[r["group_id"]]) == 2]
    write_jsonl(a.out, rows)
    print(f"{len(rows)} rows, {len({r['group_id'] for r in rows})} problems, labels {dict(Counter(r['label'] for r in rows))}")
    print("generators:", dict(Counter(r.get('generator') for r in rows)))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("human-contests"); p.add_argument("--out", required=True); p.add_argument("--split", default="train")
    p.add_argument("--max-problems", type=int, default=300); p.add_argument("--per-problem", type=int, default=3); p.set_defaults(fn=human_contests)
    p = sp.add_parser("human-folder"); p.add_argument("--root", required=True); p.add_argument("--out", required=True); p.set_defaults(fn=human_folder)
    p = sp.add_parser("human-jsonl"); p.add_argument("--problems", required=True); p.add_argument("--out", required=True); p.set_defaults(fn=human_jsonl)
    p = sp.add_parser("generate"); p.add_argument("--human", required=True); p.add_argument("--out", required=True)
    p.add_argument("--provider", choices=["anthropic", "openai"], required=True); p.add_argument("--model", required=True)
    p.add_argument("--max-problems", type=int, default=10**9); p.add_argument("--samples", type=int, default=1); p.add_argument("--sleep", type=float, default=0.3)
    p.set_defaults(fn=generate)
    p = sp.add_parser("merge"); p.add_argument("--human", required=True); p.add_argument("--ai", nargs="+", required=True); p.add_argument("--out", required=True); p.set_defaults(fn=merge)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
