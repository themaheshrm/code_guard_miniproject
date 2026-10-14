import random

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app


def synthetic_pair(i: int) -> tuple[str, str]:
    """Stylistically contrasting human/AI-like programs. ONLY for exercising the training pipeline mechanics."""
    r = random.Random(i)
    k, m = r.randint(2, 9), r.randint(10, 99)
    human = f"def f(a,b):\n  x=0\n  for i in range(a):\n    x+=i*{k}\n  if x>{m}: return x\n  return b\nprint(f({m},{k}))\n"
    ai = (
        "from typing import List\n\n\n"
        f"def compute_weighted_total(limit: int, fallback: int) -> int:\n"
        f'    """Return the weighted total of values below ``limit``.\n\n    Args:\n        limit: Upper bound.\n        fallback: Value used when below threshold.\n    """\n'
        f"    # Accumulate the running total\n    running_total = 0\n    for index in range(limit):\n        running_total += index * {k}\n"
        f"    # Compare against the threshold\n    if running_total > {m}:\n        return running_total\n    return fallback\n\n\n"
        f'if __name__ == "__main__":\n    print(compute_weighted_total({m}, {k}))\n'
    )
    return human, ai


@pytest.fixture
def pair_rows():
    rows = []
    for i in range(60):
        h, a = synthetic_pair(i)
        rows.append({"id": f"h{i}", "group_id": f"p{i}", "label": 0, "language": "python", "code": h, "generator": "human"})
        rows.append({"id": f"a{i}", "group_id": f"p{i}", "label": 1, "language": "python", "code": a, "generator": "synthetic"})
    return rows


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEGUARD_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    get_settings.cache_clear()
    with TestClient(create_app("sqlite:///:memory:")) as c:
        yield c
    get_settings.cache_clear()
