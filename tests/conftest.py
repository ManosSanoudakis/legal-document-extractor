import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def sample_truth() -> dict:
    return json.loads((ROOT / "samples" / "sample_deed.json").read_text(encoding="utf-8"))


def make_valid_afm(first8: str) -> str:
    total = sum(int(d) * 2 ** (8 - i) for i, d in enumerate(first8))
    return first8 + str(total % 11 % 10)
