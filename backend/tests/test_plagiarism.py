import random

import pytest

from app.detectors.plagiarism import Fingerprint, PlagiarismConfig, build_fingerprint, compare, compare_batch, winnow
from ml.obfuscate import TRANSFORMS, combined

CFG = PlagiarismConfig()
ORIGINAL = '''import math

def circle_area(r):
    # area of a circle
    total = math.pi * r * r
    return round(total, 2)

def collatz(n):
    steps = 0
    while n != 1:
        if n % 2 == 0:
            n //= 2
        else:
            n = 3 * n + 1
        steps += 1
    return steps

def fib(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a
'''
OTHER = '''def is_prime(n):
    if n < 2:
        return False
    for i in range(2, int(n ** 0.5) + 1):
        if n % i == 0:
            return False
    return True

def gcd(a, b):
    while b:
        a, b = b, a % b
    return a
'''


def fp(name, code, lang="python"):
    return build_fingerprint(name, code, lang, CFG)


@pytest.mark.parametrize("kind", list(TRANSFORMS) + ["combined"])
def test_obfuscated_copy_is_detected(kind):
    fn = TRANSFORMS.get(kind, combined)
    variant = fn(ORIGINAL, random.Random(3))
    assert compare(fp("a", ORIGINAL), fp("b", variant), CFG)["score"] >= 0.6, kind


def test_unrelated_programs_score_low():
    assert compare(fp("a", ORIGINAL), fp("b", OTHER), CFG)["score"] < 0.15


def test_identical_is_one_and_symmetric():
    a, b = fp("a", ORIGINAL), fp("b", ORIGINAL)
    assert compare(a, b, CFG)["score"] == 1.0
    x, y = fp("x", ORIGINAL), fp("y", OTHER)
    assert compare(x, y, CFG)["score"] == compare(y, x, CFG)["score"]


def test_copied_function_inside_larger_file_gets_line_ranges():
    mixed = OTHER + "\n" + ORIGINAL.split("def collatz")[1].join(["def collatz", ""]).split("def fib")[0]
    r = compare(fp("a", ORIGINAL), fp("b", mixed), CFG)
    assert r["lines_a"] and r["lines_b"] and r["block_matches"]


def test_batch_matrix_and_clusters():
    dup = TRANSFORMS["rename"](ORIGINAL, random.Random(1))
    res = compare_batch([fp("a.py", ORIGINAL), fp("b.py", dup), fp("c.py", OTHER)], CFG)
    assert res["matrix"][0][1] == res["matrix"][1][0] >= 0.7 and res["matrix"][0][2] < 0.2
    assert res["pairs"][0]["a"] == "a.py" and res["clusters"] == [["a.py", "b.py"]]


def test_works_for_java_and_unparseable_code_falls_back_to_tokens():
    j1 = "class A { int f(int x){ int s = 0; for (int i=0;i<x;i++){ s += i*2; } return s; } }"
    j2 = "class B { int g(int n){ int t = 0; for (int k=0;k<n;k++){ t += k*2; } return t; } }"
    assert compare(fp("a", j1, "java"), fp("b", j2, "java"), CFG)["score"] > 0.8
    broken = compare(fp("a", "def f(:\n  x = 1 + 2 * 3 + 4 * 5 + 6\n"), fp("b", "def g(:\n  y = 1 + 2 * 3 + 4 * 5 + 6\n"), CFG)
    assert broken["ast_used"] is False and broken["token_similarity"] > 0.5


def test_fingerprint_serialisation_roundtrip():
    a = fp("a", ORIGINAL)
    b = Fingerprint.from_dict(a.to_dict())
    assert compare(a, b, CFG)["score"] == 1.0


def test_winnowing_guarantee_shared_run_is_found():
    shared = [f"t{i}" for i in range(CFG.k + CFG.w)]  # >= w + k - 1 tokens
    a = winnow(["x1", "x2", "x3"] + shared + ["y1"], CFG.k, CFG.w)
    b = winnow(["q1", "q2"] + shared + ["z1", "z2", "z3"], CFG.k, CFG.w)
    assert {h for h, _ in a} & {h for h, _ in b}
