import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# The API's history database goes to a throwaway folder, never the project's data/
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="deed-history-")


@pytest.fixture
def sample_truth() -> dict:
    return json.loads((ROOT / "samples" / "sample_deed.json").read_text(encoding="utf-8"))


def make_valid_afm(first8: str) -> str:
    total = sum(int(d) * 2 ** (8 - i) for i, d in enumerate(first8))
    return first8 + str(total % 11 % 10)
