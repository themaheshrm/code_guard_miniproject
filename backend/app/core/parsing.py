"""Language detection, lexing, normalisation and AST construction.

Python uses the stdlib ``tokenize``/``ast``; Java, C, C++ and JavaScript use tree-sitter.
Submitted code is only ever parsed, never executed.
"""
from __future__ import annotations

import ast
import builtins
import hashlib
import importlib
import io
import keyword
import re
import tokenize
from dataclasses import dataclass, field

SUPPORTED_LANGUAGES = ("python", "java", "c", "cpp", "javascript")
_EXT = {
    ".py": "python", ".java": "java", ".c": "c", ".h": "c", ".cc": "cpp", ".cpp": "cpp",
    ".cxx": "cpp", ".hpp": "cpp", ".js": "javascript", ".mjs": "javascript", ".jsx": "javascript",
}


def detect_language(filename: str | None, code: str, hint: str | None = None) -> str:
    if hint and hint.lower() in SUPPORTED_LANGUAGES:
        return hint.lower()
    if filename:
        for ext, lang in _EXT.items():
            if filename.lower().endswith(ext):
                return lang
    if "#include" in code:
        return "cpp" if re.search(r"std::|iostream|\bclass\s+\w+|template\s*<", code) else "c"
    if re.search(r"\bpublic\s+(static\s+)?(class|void)\b|import\s+java\.", code):
        return "java"
    if re.search(r"\bfunction\s+\w+\s*\(|=>|\bconst\s+\w+\s*=|console\.log", code):
        return "javascript"
    return "python"


# --------------------------------------------------------------------------- tokens
@dataclass(slots=True)
class Token:
    kind: str  # id | kw | num | str | op | comment
    text: str
    line: int
    col: int = 0


_KW = {
    "python": set(keyword.kwlist),
    "java": set("abstract assert boolean break byte case catch char class const continue default do double else enum extends final finally float for goto if implements import instanceof int interface long native new package private protected public return short static strictfp super switch synchronized this throw throws transient try void volatile while var record true false null".split()),
    "c": set("auto break case char const continue default do double else enum extern float for goto if inline int long register restrict return short signed sizeof static struct switch typedef union unsigned void volatile while include define ifdef ifndef endif pragma NULL".split()),
    "javascript": set("async await break case catch class const continue debugger default delete do else export extends finally for function if import in instanceof let new of return super switch this throw try typeof var void while with yield true false null undefined".split()),
}
_KW["cpp"] = _KW["c"] | set("bool catch class constexpr delete explicit friend namespace new noexcept nullptr operator private protected public template this throw try typename using virtual true false auto override final std".split())

_KEEP_IDS = {
    "python": set(dir(builtins)),
    "java": set("String System out println print Math Integer List ArrayList Map HashMap Scanner main length size".split()),
    "c": set("printf scanf malloc free memcpy strlen main puts getchar".split()),
    "cpp": set("cout cin endl vector string map main size push_back begin end".split()),
    "javascript": set("console log Math Array Object JSON Promise length push map filter".split()),
}
_KEEP_IDS["cpp"] |= _KEEP_IDS["c"]

_LEX_BODY = r"""
 (?P<ws>\s+)
|(?P<lcomment>//[^\n]*)
|(?P<bcomment>/\*.*?\*/)
|(?P<str>"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'|`(?:\\.|[^`\\])*`)
|(?P<num>0[xX][0-9a-fA-F_]+|\d[\d_]*\.?\d*(?:[eE][+-]?\d+)?[fFlLuU]*)
|(?P<id>[A-Za-z_$][A-Za-z0-9_$]*)
|(?P<op>==|!=|<=|>=|&&|\|\||\+\+|--|\+=|-=|\*=|/=|->|=>|::|<<|>>|[^\s\w])
"""
_LEX_C = re.compile(_LEX_BODY, re.X | re.S)
_LEX_PY = re.compile(r"(?P<hcomment>\#[^\n]*)|" + _LEX_BODY.replace("(?P<lcomment>//[^\\n]*)|", "").replace("(?P<bcomment>/\\*.*?\\*/)|", ""), re.X | re.S)


def _lex_python(code: str) -> list[Token]:
    out: list[Token] = []
    fs_start = getattr(tokenize, "FSTRING_START", -1)
    fs_skip = {getattr(tokenize, "FSTRING_MIDDLE", -2), getattr(tokenize, "FSTRING_END", -3)}
    for t in tokenize.generate_tokens(io.StringIO(code).readline):
        tt, line, col = t.type, t.start[0], t.start[1]
        if tt == tokenize.NAME:
            out.append(Token("kw" if keyword.iskeyword(t.string) else "id", t.string, line, col))
        elif tt == tokenize.NUMBER:
            out.append(Token("num", t.string, line, col))
        elif tt == tokenize.STRING or tt == fs_start:
            out.append(Token("str", t.string, line, col))
        elif tt == tokenize.OP:
            out.append(Token("op", t.string, line, col))
        elif tt == tokenize.COMMENT:
            out.append(Token("comment", t.string, line, col))
        elif tt == tokenize.NEWLINE:
            out.append(Token("op", "NEWLINE", line, col))
        elif tt == tokenize.INDENT:
            out.append(Token("op", "INDENT", line, col))
        elif tt == tokenize.DEDENT:
            out.append(Token("op", "DEDENT", line, col))
        elif tt in fs_skip:
            continue
    return out


def _lex_generic(code: str, lang: str) -> list[Token]:
    rx = _LEX_PY if lang == "python" else _LEX_C
    kws = _KW[lang]
    out: list[Token] = []
    line, line_start = 1, 0
    for m in rx.finditer(code):
        kind, text = m.lastgroup, m.group()
        col = m.start() - line_start
        if kind != "ws":
            if kind in ("lcomment", "bcomment", "hcomment"):
                out.append(Token("comment", text, line, col))
            elif kind == "id":
                out.append(Token("kw" if text in kws else "id", text, line, col))
            else:
                out.append(Token(kind, text, line, col))
        nl = text.count("\n")
        if nl:
            line += nl
            line_start = m.start() + text.rfind("\n") + 1
    return out


def lex(code: str, lang: str) -> list[Token]:
    if lang == "python":
        try:
            return _lex_python(code)
        except (tokenize.TokenError, IndentationError, SyntaxError):
            pass
    return _lex_generic(code, lang)


def normalize(tokens: list[Token], lang: str) -> list[Token]:
    """Drop comments and abstract identifiers/literals so renaming does not change the stream."""
    keep = _KEEP_IDS.get(lang, set())
    out: list[Token] = []
    for t in tokens:
        if t.kind == "comment":
            continue
        if t.kind == "id":
            out.append(Token("id", t.text if t.text in keep else "ID", t.line, t.col))
        elif t.kind == "num":
            out.append(Token("num", "NUM", t.line, t.col))
        elif t.kind == "str":
            out.append(Token("str", "STR", t.line, t.col))
        else:
            out.append(t)
    return out


# --------------------------------------------------------------------------- AST
FUNC_TYPES = {
    "FunctionDef", "AsyncFunctionDef", "function_definition", "method_declaration",
    "constructor_declaration", "function_declaration", "method_definition",
}


@dataclass(slots=True)
class Node:
    type: str
    start: int
    end: int
    children: list["Node"] = field(default_factory=list)
    name: str = ""
    size: int = 1
    hash: int = 0


def _finish(n: Node) -> Node:
    n.size = 1 + sum(c.size for c in n.children)
    h = hashlib.blake2b(digest_size=8)
    h.update(n.type.encode())
    for c in n.children:
        h.update(c.hash.to_bytes(8, "big"))
    n.hash = int.from_bytes(h.digest(), "big")
    return n


_MAX_DEPTH = 300


def _is_docstring_expr(c: ast.AST) -> bool:
    return isinstance(c, ast.Expr) and isinstance(c.value, ast.Constant) and isinstance(c.value.value, str)


def _py_node(n: ast.AST, depth: int, span: tuple[int, int]) -> Node:
    s = getattr(n, "lineno", span[0])
    e = getattr(n, "end_lineno", span[1]) or s
    kids: list[Node] = []
    if depth < _MAX_DEPTH:
        for c in ast.iter_child_nodes(n):
            if isinstance(c, (ast.Load, ast.Store, ast.Del)) or _is_docstring_expr(c):
                continue
            kids.append(_py_node(c, depth + 1, (s, e)))
    name = getattr(n, "name", "") if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else ""
    return _finish(Node(type(n).__name__, s, e, kids, name))


_PUNCT = set("(){}[];,.:")
_TS_MODULES = {
    "python": "tree_sitter_python", "java": "tree_sitter_java", "c": "tree_sitter_c",
    "cpp": "tree_sitter_cpp", "javascript": "tree_sitter_javascript",
}
_TS_CACHE: dict[str, object] = {}
_TS_ERRORS: dict[str, str] = {}


def _ts_parser(lang: str):
    if lang not in _TS_CACHE:
        try:
            from tree_sitter import Language, Parser

            mod = importlib.import_module(_TS_MODULES[lang])
            _TS_CACHE[lang] = Parser(Language(mod.language()))
        except Exception as e:  # pragma: no cover - missing optional grammar
            _TS_CACHE[lang] = None
            _TS_ERRORS[lang] = f"{type(e).__name__}: {e}"
    return _TS_CACHE[lang]


def get_parser_diagnostics() -> dict[str, dict]:
    """Return availability and diagnostic info for all supported AST parser grammars."""
    diagnostics = {}
    for lang, mod_name in _TS_MODULES.items():
        parser = _ts_parser(lang)
        diagnostics[lang] = {
            "module": mod_name,
            "available": parser is not None,
            "error": _TS_ERRORS.get(lang),
        }
    return diagnostics



def _ts_name(n) -> str:
    try:
        nm = n.child_by_field_name("name")
        if nm is not None:
            return nm.text.decode(errors="ignore")
        d = n.child_by_field_name("declarator")
        stack = [d] if d is not None else []
        while stack:
            x = stack.pop(0)
            if x.type in ("identifier", "field_identifier"):
                return x.text.decode(errors="ignore")
            stack.extend(x.children)
    except Exception:  # pragma: no cover
        pass
    return ""


def _ts_node(n, depth: int) -> Node:
    kids: list[Node] = []
    if depth < _MAX_DEPTH:
        for c in n.children:
            if c.is_named or (c.type not in _PUNCT and not (c.type[0].isalnum() or c.type[0] == "_")):
                kids.append(_ts_node(c, depth + 1))
    name = _ts_name(n) if n.type in FUNC_TYPES or n.type.endswith("_declaration") or n.type.endswith("_definition") else ""
    return _finish(Node(n.type, n.start_point[0] + 1, n.end_point[0] + 1, kids, name))


def build_ast(code: str, lang: str) -> Node | None:
    """Return a hashed AST or None if the code cannot be parsed."""
    try:
        if lang == "python":
            return _py_node(ast.parse(code), 0, (1, max(1, code.count("\n") + 1)))
        parser = _ts_parser(lang)
        if parser is None:
            return None
        tree = parser.parse(code.encode("utf-8", errors="ignore"))
        return _ts_node(tree.root_node, 0)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None


def walk(root: Node):
    stack = [(root, 1)]
    while stack:
        n, d = stack.pop()
        yield n, d
        stack.extend((c, d + 1) for c in n.children)


def ast_stats(root: Node | None) -> dict[str, float]:
    if root is None:
        return {"nodes": 0, "max_depth": 0, "mean_depth": 0.0, "branching": 0.0}
    count = depth_sum = max_d = inner = kid_sum = 0
    for n, d in walk(root):
        count += 1
        depth_sum += d
        max_d = max(max_d, d)
        if n.children:
            inner += 1
            kid_sum += len(n.children)
    return {"nodes": count, "max_depth": max_d, "mean_depth": depth_sum / count, "branching": kid_sum / max(1, inner)}


def functions(root: Node | None) -> list[Node]:
    if root is None:
        return []
    return sorted((n for n, _ in walk(root) if n.type in FUNC_TYPES), key=lambda n: (n.start, n.end))
