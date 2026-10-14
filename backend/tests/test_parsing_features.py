import pytest

from app.core.features import FEATURE_NAMES, extract_features
from app.core.parsing import ast_stats, build_ast, detect_language, functions, lex, normalize

SAMPLES = {
    "python": "def add(a, b):\n    # sum\n    return a + b\n",
    "java": "public class A { int add(int a, int b) { return a + b; } }",
    "c": "#include <stdio.h>\nint add(int a, int b) { return a + b; }\n",
    "cpp": "#include <iostream>\nint add(int a, int b) { return a + b; }\nint main(){ std::cout << add(1,2); }",
    "javascript": "function add(a, b) { return a + b; } // sum",
}


@pytest.mark.parametrize("lang,src", SAMPLES.items())
def test_every_language_parses_and_finds_functions(lang, src):
    root = build_ast(src, lang)
    assert root is not None and ast_stats(root)["nodes"] > 5
    assert "add" in [f.name for f in functions(root)]
    assert not any(t.kind == "comment" for t in normalize(lex(src, lang), lang))


def test_normalisation_abstracts_identifiers_and_literals():
    a = [t.text for t in normalize(lex("x = foo(1, 'a')", "python"), "python")]
    b = [t.text for t in normalize(lex("total = bar(99, 'zzz')", "python"), "python")]
    assert a == b


def test_syntax_error_python_degrades_gracefully():
    assert build_ast("def f(:\n", "python") is None
    assert len(lex("def f(:\n", "python")) > 0


@pytest.mark.parametrize("name,code,expected", [("a.py", "x=1", "python"), ("A.java", "x", "java"), ("m.cpp", "x", "cpp"),
                                                 ("x", "#include <stdio.h>\nint main(){}", "c"), ("x", "console.log(1)", "javascript")])
def test_detect_language(name, code, expected):
    assert detect_language(name, code) == expected


def test_features_are_complete_and_finite():
    f = extract_features(SAMPLES["python"] * 3, "python")
    assert list(f) == FEATURE_NAMES and all(v == v and abs(v) < 1e9 for v in f.values())
    assert f["n_functions"] == 3 and f["comment_line_ratio"] > 0


def test_features_separate_styles():
    from tests.conftest import synthetic_pair

    h, a = synthetic_pair(1)
    fh, fa = extract_features(h, "python"), extract_features(a, "python")
    assert fa["docstring_ratio"] > fh["docstring_ratio"] and fa["id_avg_len"] > fh["id_avg_len"]


def test_empty_and_tiny_inputs_do_not_crash():
    for lang in SAMPLES:
        extract_features("x", lang)
        extract_features("\n\n", lang)
