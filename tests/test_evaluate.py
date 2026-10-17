import copy

import pytest

from deed_extractor import evaluate
from deed_extractor.evaluate import RunResult, run_evaluation
from deed_extractor.schema import ExtractionResult


@pytest.fixture
def fake_runs(monkeypatch, sample_truth):
    """Stub the model calls: each model returns a given deed after a given time."""
    def install(outputs: dict[str, tuple[dict, float]]):
        def run_once(images, texts, key, model):
            deed, elapsed = outputs[model]
            if isinstance(deed, Exception):
                return RunResult(model, {}, 0.0, error=str(deed), exception=deed)
            result = ExtractionResult(deed=deed, meta={"model": model, "elapsed_seconds": elapsed})
            return RunResult(model, evaluate.completeness_score(deed), elapsed, result=result)

        monkeypatch.setattr(evaluate, "pdf_to_images", lambda pdf_path, output_dir: [])
        monkeypatch.setattr(evaluate, "pdf_page_texts", lambda pdf_path: [])
        monkeypatch.setattr(evaluate, "_run_once", run_once)
    return install


def test_tie_goes_to_the_faster_model(fake_runs, sample_truth):
    fake_runs({"slow": (copy.deepcopy(sample_truth), 20.0), "fast": (copy.deepcopy(sample_truth), 9.0)})
    winner = run_evaluation("x.pdf", "key", models=["slow", "fast"], truth=sample_truth).winner
    assert winner.model_dump() == {"accuracy": "fast", "basis": "accuracy", "tie": True, "speed": "fast"}


def test_more_accurate_model_wins_even_if_slower(fake_runs, sample_truth):
    wrong = copy.deepcopy(sample_truth)
    wrong["transaction"]["price"] = 1
    fake_runs({"slow": (copy.deepcopy(sample_truth), 20.0), "fast": (wrong, 9.0)})
    report = run_evaluation("x.pdf", "key", models=["slow", "fast"], truth=sample_truth)
    assert report.winner.model_dump() == {"accuracy": "slow", "basis": "accuracy", "tie": False, "speed": "fast"}
    assert report.models[1].accuracy.mismatches[0].field == "transaction.price"
    assert [d.field for d in report.field_diffs] == ["transaction.price"]


def test_all_models_failing_can_raise(fake_runs, sample_truth):
    """A job wants the error itself (e.g. a rejected key), not a report of two failures."""
    fake_runs({"a": (PermissionError("bad key"), 0.0), "b": (PermissionError("bad key"), 0.0)})
    report = run_evaluation("x.pdf", "key", models=["a", "b"], truth=sample_truth)
    assert [m.error for m in report.models] == ["bad key", "bad key"]
    assert report.winner is None and report.models[0].completeness is None
    with pytest.raises(PermissionError):
        run_evaluation("x.pdf", "key", models=["a", "b"], truth=sample_truth, raise_if_all_failed=True)


def test_raw_results_keep_each_full_answer(fake_runs, sample_truth):
    fake_runs({"a": (copy.deepcopy(sample_truth), 1.0), "b": (ValueError("boom"), 0.0)})
    raw = run_evaluation("x.pdf", "key", models=["a", "b"], truth=sample_truth).model_dump(mode="json")["raw_results"]
    assert raw["a"]["deed"] == sample_truth and raw["a"]["meta"]["model"] == "a"
    assert raw["b"] is None
