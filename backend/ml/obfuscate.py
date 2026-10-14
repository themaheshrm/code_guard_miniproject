"""Semantics-preserving-looking obfuscations used to test the plagiarism engine (Python sources)."""
from __future__ import annotations

import ast
import builtins
import io
import random
import tokenize

_BUILTINS = set(dir(builtins))
_DEAD = ["_dbg = 0", "_tmp = [i for i in range(0)]", "if __debug__ and False:\n    pass", "_unused = len('x') * 3 + 1", "pass"]


def _scope_names(fn: ast.AST) -> set[str]:
    names = {a.arg for a in ast.walk(fn) if isinstance(a, ast.arg)}
    names |= {n.id for n in ast.walk(fn) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
    return {n for n in names if n not in _BUILTINS and n not in ("self", "cls") and not n.startswith("__")}


def rename_identifiers(src: str, rng: random.Random) -> str:
    tree = ast.parse(src)
    counter = [0]

    def fresh(prefix: str) -> str:
        counter[0] += 1
        return f"{prefix}{rng.choice('xyzqk')}{counter[0]}"

    top_funcs = {n.name for n in tree.body if isinstance(n, ast.FunctionDef) and not n.name.startswith("__")}
    fmap = {n: fresh("fn_") for n in top_funcs}
    scopes = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    for fn in scopes:
        local = {n: fresh("v") for n in _scope_names(fn)}
        for n in ast.walk(fn):
            if isinstance(n, ast.arg) and n.arg in local:
                n.arg = local[n.arg]
            elif isinstance(n, ast.Name) and n.id in local:
                n.id = local[n.id]
    if not scopes:  # script-style file: rename module-level variables
        local = {n: fresh("v") for n in _scope_names(tree)}
        for n in ast.walk(tree):
            if isinstance(n, ast.Name) and n.id in local:
                n.id = local[n.id]
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.name in fmap:
            n.name = fmap[n.name]
        elif isinstance(n, ast.Name) and n.id in fmap:
            n.id = fmap[n.id]
    return ast.unparse(ast.fix_missing_locations(tree))


def _names(node: ast.AST) -> tuple[set[str], set[str]]:
    loads = {n.id for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    stores = {n.id for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
    return loads, stores


def reorder_statements(src: str, rng: random.Random) -> str:
    tree = ast.parse(src)
    defs = [i for i, n in enumerate(tree.body) if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
    if len(defs) > 1:
        picked = [tree.body[i] for i in defs]
        rng.shuffle(picked)
        for i, n in zip(defs, picked):
            tree.body[i] = n
    for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))] + [tree]:
        body = fn.body
        for i in range(len(body) - 1):
            a, b = body[i], body[i + 1]
            if isinstance(a, (ast.Assign, ast.Expr)) and isinstance(b, (ast.Assign, ast.Expr)):
                la, sa = _names(a)
                lb, sb = _names(b)
                if not (sa & (lb | sb)) and not (sb & la) and rng.random() < 0.6:
                    body[i], body[i + 1] = b, a
    return ast.unparse(ast.fix_missing_locations(tree))


def edit_comments(src: str, rng: random.Random) -> str:
    """Strip existing comments and insert new ones before some statements."""
    lines = src.splitlines()
    stmt_starts, new_start = set(), True
    try:
        for t in tokenize.generate_tokens(io.StringIO(src).readline):
            if t.type == tokenize.COMMENT:
                row = t.start[0] - 1
                lines[row] = lines[row][: t.start[1]].rstrip()
            elif t.type in (tokenize.NL, tokenize.INDENT, tokenize.DEDENT):
                continue
            elif t.type == tokenize.NEWLINE:
                new_start = True
            elif new_start:
                stmt_starts.add(t.start[0] - 1)
                new_start = False
    except (tokenize.TokenError, IndentationError):
        return src
    out = []
    for i, ln in enumerate(lines):
        if i in stmt_starts and rng.random() < 0.35:
            indent = ln[: len(ln) - len(ln.lstrip())]
            out.append(f"{indent}# {rng.choice(['step', 'note', 'TODO check', 'helper', 'compute value'])}")
        out.append(ln)
    return "\n".join(out) + "\n"


def insert_dead_code(src: str, rng: random.Random) -> str:
    tree = ast.parse(src)
    bodies = [n.body for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))] or [tree.body]
    for body in bodies:
        for _ in range(max(1, len(body) // 4)):
            stmt = ast.parse(rng.choice(_DEAD)).body[0]
            pos = rng.randint(1 if body and isinstance(body[0], ast.Expr) else 0, len(body))
            body.insert(pos, stmt)
    return ast.unparse(ast.fix_missing_locations(tree))


TRANSFORMS = {"rename": rename_identifiers, "reorder": reorder_statements, "comments": edit_comments, "dead_code": insert_dead_code}


def combined(src: str, rng: random.Random) -> str:
    out = src
    for name in ("reorder", "dead_code", "rename", "comments"):
        out = TRANSFORMS[name](out, rng)
    return out
