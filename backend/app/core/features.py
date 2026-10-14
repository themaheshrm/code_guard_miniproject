"""Stylometric features for the feature-based (XGBoost) AI-code detector."""
from __future__ import annotations

import math
import re
import statistics
from collections import Counter

from .parsing import Token, ast_stats, build_ast, functions, lex, normalize

_SNAKE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)+$")
_CAMEL = re.compile(r"^[a-z]+([A-Z][a-z0-9]*)+$")
_UPPER = re.compile(r"^[A-Z][A-Z0-9_]+$")

FEATURE_NAMES = [
    "n_lines", "blank_line_ratio", "avg_line_len", "std_line_len", "max_line_len", "line_len_cv",
    "comment_line_ratio", "comment_char_ratio", "inline_comment_ratio", "docstring_ratio", "comments_per_function",
    "n_tokens", "token_entropy", "raw_token_entropy", "magic_number_ratio", "string_token_ratio",
    "id_unique_ratio", "id_avg_len", "id_std_len", "id_single_char_ratio", "id_snake_ratio",
    "id_camel_ratio", "id_upper_ratio", "id_digit_ratio", "id_long_ratio",
    "ast_nodes", "ast_max_depth", "ast_mean_depth", "ast_branching", "nodes_per_line",
    "n_functions", "avg_func_len", "max_func_len", "funcs_per_100_lines",
    "max_nesting", "trailing_ws_ratio", "tab_indent_ratio", "indent_consistency", "comma_space_ratio",
    "double_quote_ratio", "type_hint_ratio", "try_per_function", "main_guard", "print_per_line", "fstring_ratio",
]


def _entropy(items: list[str]) -> float:
    if not items:
        return 0.0
    c, n = Counter(items), len(items)
    return -sum(v / n * math.log2(v / n) for v in c.values())


def _std(xs: list[float]) -> float:
    return statistics.pstdev(xs) if len(xs) > 1 else 0.0


def _ratio(a: float, b: float) -> float:
    return a / b if b else 0.0


def _nesting(tokens: list[Token], lang: str) -> int:
    depth = best = 0
    for t in tokens:
        if t.kind != "op":
            continue
        if t.text in ("INDENT", "{"):
            depth += 1
            best = max(best, depth)
        elif t.text in ("DEDENT", "}"):
            depth = max(0, depth - 1)
    return best


def _python_extras(code: str) -> dict[str, float]:
    import ast as pyast

    try:
        tree = pyast.parse(code)
    except SyntaxError:
        return {}
    funcs = [n for n in pyast.walk(tree) if isinstance(n, (pyast.FunctionDef, pyast.AsyncFunctionDef))]
    with_doc = sum(1 for f in funcs if pyast.get_docstring(f))
    annotated = total = 0
    for f in funcs:
        for a in f.args.args + f.args.kwonlyargs:
            if a.arg in ("self", "cls"):
                continue
            total += 1
            annotated += a.annotation is not None
        total += 1
        annotated += f.returns is not None
    tries = sum(isinstance(n, pyast.Try) for n in pyast.walk(tree))
    guard = any(
        isinstance(n, pyast.If) and isinstance(n.test, pyast.Compare) and isinstance(n.test.left, pyast.Name)
        and n.test.left.id == "__name__" for n in tree.body
    )
    return {"docstring_ratio": _ratio(with_doc, len(funcs)), "type_hint_ratio": _ratio(annotated, total),
            "try_per_function": _ratio(tries, max(1, len(funcs))), "main_guard": float(guard)}


def extract_features(code: str, lang: str) -> dict[str, float]:
    f = dict.fromkeys(FEATURE_NAMES, 0.0)
    lines = code.splitlines()
    nonblank = [ln for ln in lines if ln.strip()]
    lens = [len(ln) for ln in nonblank]
    n_nb = max(1, len(nonblank))
    f["n_lines"] = len(lines)
    f["blank_line_ratio"] = _ratio(len(lines) - len(nonblank), len(lines))
    f["avg_line_len"] = statistics.fmean(lens) if lens else 0.0
    f["std_line_len"] = _std(lens)
    f["max_line_len"] = max(lens) if lens else 0
    f["line_len_cv"] = _ratio(f["std_line_len"], f["avg_line_len"])

    toks = lex(code, lang)
    code_toks = [t for t in toks if t.kind != "comment"]
    comments = [t for t in toks if t.kind == "comment"]
    c_lines: set[int] = set()
    inline = 0
    for c in comments:
        span = c.text.count("\n") + 1
        c_lines.update(range(c.line, c.line + span))
        if c.line - 1 < len(lines) and lines[c.line - 1][:c.col].strip():
            inline += 1
    f["comment_line_ratio"] = len(c_lines) / n_nb
    f["comment_char_ratio"] = _ratio(sum(len(c.text) for c in comments), max(1, len(code)))
    f["inline_comment_ratio"] = _ratio(inline, len(comments))

    norm = [t.text for t in normalize(toks, lang)]
    ids = [t.text for t in code_toks if t.kind == "id"]
    f["n_tokens"] = len(code_toks)
    f["token_entropy"] = _entropy(norm)
    f["raw_token_entropy"] = _entropy([t.text for t in code_toks])
    nums = [t.text for t in code_toks if t.kind == "num"]
    f["magic_number_ratio"] = _ratio(sum(1 for x in nums if x not in ("0", "1", "2")), len(code_toks))
    f["string_token_ratio"] = _ratio(sum(t.kind == "str" for t in code_toks), len(code_toks))
    uniq = set(ids)
    id_lens = [len(i) for i in ids]
    f["id_unique_ratio"] = _ratio(len(uniq), len(ids))
    f["id_avg_len"] = statistics.fmean(id_lens) if id_lens else 0.0
    f["id_std_len"] = _std(id_lens)
    f["id_single_char_ratio"] = _ratio(sum(len(i) == 1 for i in ids), len(ids))
    f["id_snake_ratio"] = _ratio(sum(bool(_SNAKE.match(i)) for i in ids), len(ids))
    f["id_camel_ratio"] = _ratio(sum(bool(_CAMEL.match(i)) for i in ids), len(ids))
    f["id_upper_ratio"] = _ratio(sum(bool(_UPPER.match(i)) for i in ids), len(ids))
    f["id_digit_ratio"] = _ratio(sum(any(ch.isdigit() for ch in i) for i in ids), len(ids))
    f["id_long_ratio"] = _ratio(sum(len(i) >= 12 for i in ids), len(ids))

    root = build_ast(code, lang)
    st = ast_stats(root)
    f["ast_nodes"], f["ast_max_depth"], f["ast_mean_depth"], f["ast_branching"] = st["nodes"], st["max_depth"], st["mean_depth"], st["branching"]
    f["nodes_per_line"] = _ratio(st["nodes"], n_nb)
    fns = functions(root)
    fl = [x.end - x.start + 1 for x in fns]
    f["n_functions"] = len(fns)
    f["avg_func_len"] = statistics.fmean(fl) if fl else 0.0
    f["max_func_len"] = max(fl) if fl else 0
    f["funcs_per_100_lines"] = 100 * _ratio(len(fns), n_nb)
    f["comments_per_function"] = _ratio(len(comments), max(1, len(fns)))
    f["max_nesting"] = _nesting(code_toks, lang)

    f["trailing_ws_ratio"] = _ratio(sum(ln != ln.rstrip() for ln in lines), len(lines))
    indents = [len(ln) - len(ln.lstrip(" \t")) for ln in nonblank if ln[:1] in (" ", "\t")]
    f["tab_indent_ratio"] = _ratio(sum(ln.startswith("\t") for ln in nonblank), n_nb)
    spaced = [i for i, ln in zip(indents, [x for x in nonblank if x[:1] in (" ", "\t")]) if not ln.startswith("\t")] if indents else []
    unit = min((i for i in spaced if i > 0), default=0)
    f["indent_consistency"] = _ratio(sum(i % unit == 0 for i in spaced), len(spaced)) if unit else 1.0
    commas = len(re.findall(r",", code))
    f["comma_space_ratio"] = _ratio(len(re.findall(r", ", code)), commas) if commas else 1.0
    strs = [t.text for t in code_toks if t.kind == "str"]
    f["double_quote_ratio"] = _ratio(sum('"' in s[:3] for s in strs), len(strs)) if strs else 0.5
    f["fstring_ratio"] = _ratio(sum(s[:2].lower() in ('f"', "f'") for s in strs), len(strs))
    f["print_per_line"] = _ratio(sum(1 for t in code_toks if t.text in ("print", "printf", "println", "cout", "log")), n_nb)

    if lang == "python":
        f.update(_python_extras(code))
    return {k: float(f[k]) for k in FEATURE_NAMES}


def feature_vector(code: str, lang: str) -> list[float]:
    d = extract_features(code, lang)
    return [d[k] for k in FEATURE_NAMES]
