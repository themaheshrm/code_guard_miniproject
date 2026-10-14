"""Plagiarism engine: k-gram winnowing on normalised tokens + AST subtree matching.

Token winnowing (Schleimer et al., 2003) catches copied token runs after identifier/literal/comment
changes. AST subtree matching is order-independent, so reordered statements/functions and inserted
dead code still match at the sub-block level. Both are reported along with a combined score.
"""
from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from ..core.parsing import Node, build_ast, lex, normalize, walk


@dataclass
class PlagiarismConfig:
    k: int = 8
    w: int = 5
    min_subtree: int = 6
    token_weight: float = 0.5
    threshold: float = 0.5


@dataclass
class Fingerprint:
    name: str
    language: str
    n_tokens: int
    n_lines: int
    winnow: list[tuple[int, int]]            # (hash, token position)
    token_lines: list[int]                   # source line per normalised token
    ast_ok: bool
    ast_total: int
    ast_counts: dict[int, int]               # subtree hash -> multiplicity (size >= min_subtree)
    ast_ranges: dict[int, list[tuple[int, int, int]]]  # hash -> [(start, end, size)]
    sha256: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name, "language": self.language, "n_tokens": self.n_tokens, "n_lines": self.n_lines,
            "winnow": self.winnow, "token_lines": self.token_lines, "ast_ok": self.ast_ok,
            "ast_total": self.ast_total, "ast_counts": {str(k): v for k, v in self.ast_counts.items()},
            "ast_ranges": {str(k): v for k, v in self.ast_ranges.items()}, "sha256": self.sha256,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Fingerprint":
        return cls(
            d["name"], d["language"], d["n_tokens"], d["n_lines"], [tuple(x) for x in d["winnow"]],
            d["token_lines"], d["ast_ok"], d["ast_total"],
            {int(k): v for k, v in d["ast_counts"].items()},
            {int(k): [tuple(r) for r in v] for k, v in d["ast_ranges"].items()}, d.get("sha256", ""),
        )


def _h(parts: list[str]) -> int:
    return int.from_bytes(hashlib.blake2b(" ".join(parts).encode(), digest_size=8).digest(), "big")


def winnow(tokens: list[str], k: int, w: int) -> list[tuple[int, int]]:
    """Return the winnowing fingerprint as (hash, position) pairs (rightmost minimum per window)."""
    if len(tokens) < k:
        return [(_h(tokens), 0)] if tokens else []
    hashes = [_h(tokens[i:i + k]) for i in range(len(tokens) - k + 1)]
    if len(hashes) <= w:
        m = min(hashes)
        return [(m, len(hashes) - 1 - hashes[::-1].index(m))]
    chosen: dict[int, int] = {}
    last = -1
    for i in range(len(hashes) - w + 1):
        win = hashes[i:i + w]
        m = min(win)
        pos = i + w - 1 - win[::-1].index(m)
        if pos != last:
            chosen[pos] = m
            last = pos
    return sorted(((h, p) for p, h in chosen.items()), key=lambda x: x[1])


def build_fingerprint(name: str, code: str, lang: str, cfg: PlagiarismConfig) -> Fingerprint:
    toks = normalize(lex(code, lang), lang)
    texts = [t.text for t in toks]
    root = build_ast(code, lang)
    counts: Counter[int] = Counter()
    ranges: dict[int, list[tuple[int, int, int]]] = defaultdict(list)
    total = 0
    if root is not None:
        for n, _ in walk(root):
            total += 1
            if n.size >= cfg.min_subtree:
                counts[n.hash] += 1
                ranges[n.hash].append((n.start, n.end, n.size))
    return Fingerprint(
        name=name, language=lang, n_tokens=len(texts), n_lines=code.count("\n") + 1,
        winnow=winnow(texts, cfg.k, cfg.w), token_lines=[t.line for t in toks],
        ast_ok=root is not None, ast_total=total, ast_counts=dict(counts), ast_ranges=dict(ranges),
        sha256=hashlib.sha256(code.encode("utf-8", errors="ignore")).hexdigest(),
    )


def _merge_lines(lines: set[int]) -> list[list[int]]:
    out: list[list[int]] = []
    for ln in sorted(lines):
        if out and ln <= out[-1][1] + 1:
            out[-1][1] = ln
        else:
            out.append([ln, ln])
    return out


def _matched_lines(fa: Fingerprint, other_hashes: set[int], k: int) -> set[int]:
    lines: set[int] = set()
    for h, pos in fa.winnow:
        if h in other_hashes:
            for p in range(pos, min(pos + k, len(fa.token_lines))):
                lines.add(fa.token_lines[p])
    return lines


def _ast_match(a: Fingerprint, b: Fingerprint) -> tuple[int, list[dict]]:
    """Greedy top-down matching of A's subtrees against B's multiset. Returns (covered nodes of A, pairs)."""
    # Rebuild descending order by size: larger subtrees first so nested ones are not double counted.
    remaining = dict(b.ast_counts)
    b_ranges = {h: list(v) for h, v in b.ast_ranges.items()}
    items = sorted(((s, e, size, h) for h, rs in a.ast_ranges.items() for (s, e, size) in rs), key=lambda x: -x[2])
    covered_spans: list[tuple[int, int]] = []
    covered_nodes = 0
    pairs: list[dict] = []
    for s, e, size, h in items:
        if remaining.get(h, 0) <= 0:
            continue
        if any(cs <= s and e <= ce and (e - s) < (ce - cs) + 1 and (cs, ce) != (s, e) for cs, ce in covered_spans):
            continue  # nested inside an already matched larger subtree
        remaining[h] -= 1
        bs, be, _ = b_ranges[h].pop(0)
        covered_nodes += size
        covered_spans.append((s, e))
        pairs.append({"a": [s, e], "b": [bs, be], "size": size})
    return min(covered_nodes, a.ast_total), pairs


def compare(a: Fingerprint, b: Fingerprint, cfg: PlagiarismConfig) -> dict:
    ha, hb = {h for h, _ in a.winnow}, {h for h, _ in b.winnow}
    inter = ha & hb
    tok_ab = len(inter) / len(ha) if ha else 0.0
    tok_ba = len(inter) / len(hb) if hb else 0.0
    token_sim = (tok_ab + tok_ba) / 2

    ast_sim = 0.0
    pairs: list[dict] = []
    if a.ast_ok and b.ast_ok and a.ast_total and b.ast_total:
        cov_a, pairs = _ast_match(a, b)
        cov_b, _ = _ast_match(b, a)
        ast_sim = (cov_a / a.ast_total + cov_b / b.ast_total) / 2
        score = cfg.token_weight * token_sim + (1 - cfg.token_weight) * ast_sim
    else:
        score = token_sim  # AST unavailable (syntax error / unsupported grammar)

    return {
        "a": a.name, "b": b.name, "score": round(score, 4), "token_similarity": round(token_sim, 4),
        "ast_similarity": round(ast_sim, 4), "ast_used": a.ast_ok and b.ast_ok,
        "flagged": score >= cfg.threshold,
        "lines_a": _merge_lines(_matched_lines(a, inter, cfg.k)),
        "lines_b": _merge_lines(_matched_lines(b, inter, cfg.k)),
        "block_matches": sorted(pairs, key=lambda p: -p["size"])[:25],
    }


def compare_batch(fps: list[Fingerprint], cfg: PlagiarismConfig) -> dict:
    n = len(fps)
    matrix = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    pairs: list[dict] = []
    for i in range(n):
        for j in range(i + 1, n):
            r = compare(fps[i], fps[j], cfg)
            matrix[i][j] = matrix[j][i] = r["score"]
            pairs.append(r)
    pairs.sort(key=lambda p: -p["score"])
    return {"names": [f.name for f in fps], "matrix": matrix, "pairs": pairs, "clusters": clusters(fps, matrix, cfg.threshold)}


def clusters(fps: list[Fingerprint], matrix: list[list[float]], threshold: float) -> list[list[str]]:
    """Connected components over pairs scoring >= threshold (groups of mutually similar submissions)."""
    n = len(fps)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        for j in range(i + 1, n):
            if matrix[i][j] >= threshold:
                parent[find(i)] = find(j)
    groups: dict[int, list[str]] = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(fps[i].name)
    return [g for g in groups.values() if len(g) > 1]
