import copy

import pytest

import evaluate
from evaluate import RunResult, run_evaluation


@pytest.fixture
def fake_runs(monkeypatch, sample_truth):
    """Stub the model calls: each model returns a given deed after a given time."""
    def install(outputs: dict[str, tuple[dict, float]]):
        monkeypatch.setattr(evaluate, "pdf_to_images", lambda pdf_path, output_dir: [])
        monkeypatch.setattr(
            evaluate, "_run_once",
            lambda images, key, model: RunResult(model, {"overall_pct": 100}, outputs[model][1], raw=outputs[model][0]),
        )
    return install


def test_tie_goes_to_the_faster_model(fake_runs, sample_truth):
    fake_runs({"slow": (copy.deepcopy(sample_truth), 20.0), "fast": (copy.deepcopy(sample_truth), 9.0)})
    winner = run_evaluation("x.pdf", "key", models=["slow", "fast"], truth=sample_truth)["winner"]
    assert winner == {"accuracy": "fast", "basis": "accuracy", "tie": True, "speed": "fast"}


def test_more_accurate_model_wins_even_if_slower(fake_runs, sample_truth):
    wrong = copy.deepcopy(sample_truth)
    wrong["transaction"]["price"] = 1
    fake_runs({"slow": (copy.deepcopy(sample_truth), 20.0), "fast": (wrong, 9.0)})
    winner = run_evaluation("x.pdf", "key", models=["slow", "fast"], truth=sample_truth)["winner"]
    assert winner == {"accuracy": "slow", "basis": "accuracy", "tie": False, "speed": "fast"}
