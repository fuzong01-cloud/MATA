import json
from types import SimpleNamespace

import pytest

from evaluation import metrics
from evaluation.metrics import retrieval_scores, valid_citations
from evaluation.runner import append_event, ledger_state, read_events, run
from app.core.config import settings


def fixture_snapshot():
    return {"snapshot_sha256": "fixed", "model": "test-model", "cases": [
        {"id": "T01", "kind": "text", "type": "knowledge", "module": "Web开发",
         "question": "字段对应？", "retrieved": [{"filename": "课件", "slide_number": 1,
         "module": "Web开发", "excerpt": "字段应对应"}],
         "gold": [{"filename": "课件", "slide_number": 1}]},
    ]}


def test_cap_and_resume_never_repeat_a_registered_call(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "qwen_model", "test-model")
    calls = []

    class Client:
        def __init__(self):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="字段应对应 [1]"))],
                                   usage=SimpleNamespace(prompt_tokens=10, completion_tokens=4))

        def close(self):
            pass

    path = tmp_path / "ledger.jsonl"
    snapshot = fixture_snapshot()
    first = run(snapshot, path, cap=1, client_factory=Client)
    assert first["calls_used"] == 1
    assert len(calls) == 1
    second = run(snapshot, path, cap=1, client_factory=Client)
    assert second["calls_used"] == 1
    assert len(calls) == 1
    assert ledger_state(read_events(path))[0] == 1


def test_interrupted_request_counts_against_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "qwen_model", "test-model")
    path = tmp_path / "ledger.jsonl"
    append_event(path, {"event": "start", "job": "T01:single_rag:answer", "snapshot_sha256": "fixed"})
    result = run(fixture_snapshot(), path, cap=1, client_factory=lambda: pytest.fail("must not call"))
    assert result["pending"] == 1
    assert result["calls_remaining"] == 0


def test_snapshot_mismatch_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "qwen_model", "test-model")
    path = tmp_path / "ledger.jsonl"
    append_event(path, {"event": "start", "job": "T01:single_rag:answer", "snapshot_sha256": "other"})
    with pytest.raises(ValueError, match="快照不一致"):
        run(fixture_snapshot(), path, client_factory=lambda: None)


def test_retrieval_and_citation_metrics_are_distinct():
    cases = [fixture_snapshot()["cases"][0], {
        "id": "T02", "kind": "text", "gold": [{"filename": "另一课件", "slide_number": 2}],
        "retrieved": [{"filename": "另一课件", "slide_number": 3}],
    }]
    score = retrieval_scores(cases)
    assert score["recall_at_5"] == 0.5
    assert score["source_document_hit_rate"] == 1.0
    assert valid_citations("一个没有事实依据的结论 [1]", 1)
    assert not valid_citations("不存在的编号 [2]", 1)


def test_manual_review_distinguishes_not_applicable_from_failure(tmp_path, monkeypatch):
    path = tmp_path / "review.csv"
    path.write_text("job,case_id,arm,key_points_total,key_points_met,factual_error,source_support,uncertainty_correct,review_note\n"
                    "T01:single_no_rag:answer,T01,single_no_rag,2,2,0,NA,1,checked\n",
                    encoding="utf-8")
    monkeypatch.setattr(metrics, "REVIEW_FILE", path)
    result = metrics.review_scores()
    assert result["complete"]
    assert result["by_arm"]["single_no_rag"]["source_support_rate"] is None


def test_second_runner_cannot_share_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "qwen_model", "test-model")
    path = tmp_path / "ledger.jsonl"
    path.with_suffix(".jsonl.lock").write_text("123", encoding="utf-8")
    with pytest.raises(RuntimeError, match="占用账本"):
        run(fixture_snapshot(), path, client_factory=lambda: None)
