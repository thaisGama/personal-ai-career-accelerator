"""Day-bound quiz snapshots, completion, and append-only history without paid calls."""

import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agent import tools
from src.agent.learning_progress_store import append_week_from_plan, update_day_learning_unit_path
from src.core.services.quiz_service import generate_day_quiz_service, evaluate_day_quiz_service
from src.core.services.roadmap_context import read_progress, resolve_quiz_day, quiz_day_identity, preserve_quiz_draft


QUIZ = "<<QUIZ>>\nDay quiz\nQ1) Explain the selected day's concept.\n<<ANSWER_KEY>>\nQ1: A grounded explanation.\n<<RUBRIC>>\nClear and accurate."
PLAN = "# Week 1 Learning Plan\n\n🧩 Learning Days (10–30 min)\n- **Day 1 (20 min): Understanding API Gateway**\n- **Day 2 (20 min): Understanding ALB**\n"


@pytest.fixture
def days(tmp_path, monkeypatch):
    path = tmp_path / "data" / "learning_progress.json"
    append_week_from_plan(path, PLAN, roadmap_id="alpha")
    append_week_from_plan(path, PLAN, roadmap_id="beta")
    unit = tmp_path / "docs" / "learning_units" / "gateway.md"
    unit.parent.mkdir(parents=True)
    unit.write_text("# Gateway\nDAY ONE LESSON: API authorization and routing.")
    update_day_learning_unit_path(path, "day_001", "docs/learning_units/gateway.md")
    monkeypatch.setattr(tools, "call_llm", lambda **kw: QUIZ)
    weeks, _ = read_progress(tmp_path)
    return tmp_path, weeks


def test_selected_day_overrides_recommendation_and_incomplete_selection_blocks(days):
    root, weeks = days
    current, error = resolve_quiz_day(weeks, "alpha")
    assert error is None and current["day"]["day_id"] == "day_001"
    selection = {"roadmap_id": "alpha", "week_id": "week_001", "day_id": "day_002"}
    explicit, error = resolve_quiz_day(weeks, "alpha", selection)
    assert error is None and explicit["day"]["topic"] == "Understanding ALB"
    weeks[0]["days"][1]["topic"] = ""
    assert resolve_quiz_day(weeks, "alpha", selection)[0] is None
    assert "incomplete" in resolve_quiz_day(weeks, "alpha", selection)[1]
    assert resolve_quiz_day(weeks, "alpha", {**selection, "day_id": "missing"})[0] is None
    assert resolve_quiz_day(weeks, None) == (None, None)


def test_generation_is_scoped_to_day_objectives_and_saved_material(days, monkeypatch):
    root, weeks = days
    progress_path = root / "data" / "learning_progress.json"
    data = json.loads(progress_path.read_text())
    data["weeks"][0]["days"][0]["learning_objectives"] = ["Explain authorization"]
    progress_path.write_text(json.dumps(data))
    (root / "data" / "tasks.csv").write_text("roadmap_id,title\nalpha,UNRELATED ROADMAP TASK\n")
    captured = []
    monkeypatch.setattr(tools, "call_llm", lambda **kw: captured.append(kw) or QUIZ)
    context, _ = resolve_quiz_day(weeks, "alpha")
    result = generate_day_quiz_service(identity=quiz_day_identity(context), model="mock", base_dir=root)
    prompt = captured[0]["user_prompt"]
    assert "Topic: Understanding API Gateway" in prompt
    assert "DAY ONE LESSON" in prompt and "Explain authorization" in prompt
    assert "Understanding ALB" not in prompt and "UNRELATED ROADMAP TASK" not in prompt
    assert result["binding"]["day_id"] == "day_001"
    assert result["binding"]["week_id"] == "week_001"
    assert result["binding"]["roadmap_id"] == "alpha"


@pytest.mark.parametrize("decision,result_label,status", [("MOVE_ON", "PASS", "PASSED"), ("REPEAT", "FAIL", "NEEDS_REVIEW")])
def test_snapshot_evaluation_updates_original_day_only_and_preserves_history(days, monkeypatch, decision, result_label, status):
    root, weeks = days
    identity = quiz_day_identity(resolve_quiz_day(weeks, "alpha")[0])
    first = generate_day_quiz_service(identity=identity, model="mock", base_dir=root)
    first_path = Path(first["quiz_path"])
    # A second generation changes the day's current quiz path; the first quiz remains valid.
    monkeypatch.setattr(tools, "call_llm", lambda **kw: QUIZ.replace("Day quiz", "Replacement quiz"))
    second = generate_day_quiz_service(identity=identity, model="mock", base_dir=root)
    assert first["quiz_path"] != second["quiz_path"] and first_path.read_text() == first["quiz_markdown"]
    identity.update(roadmap_id="beta", week_id="week_002", day_id="day_003")
    captured = []
    evaluation = {"move_on_decision": decision, "eval_block": "Weak areas: Explain routing", "score": 8}
    monkeypatch.setattr(tools, "evaluate_micro_quiz", lambda **kw: captured.append(kw) or evaluation)
    history = root / "data" / "quiz_results.jsonl"
    previous = '{"task_id":"historical","score":0.8}\n'
    history.write_text(previous)
    evaluate_day_quiz_service(binding=first["binding"], quiz_markdown=first["quiz_markdown"],
                              learner_answers="Original answers", model="mock", base_dir=root)
    saved, _ = read_progress(root)
    assert saved[0]["days"][0]["quiz_result"] == result_label
    assert saved[0]["days"][0]["status"] == status
    assert all(not d["quiz_result"] for w in saved for d in w["days"] if d["day_id"] != "day_001")
    assert captured[0]["quiz_markdown"] == first["quiz_markdown"]
    assert captured[0]["topic"] == "Understanding API Gateway"
    assert history.read_text().startswith(previous)
    row = json.loads(history.read_text().splitlines()[-1])
    assert row["day_id"] == "day_001" and row["roadmap_id"] == "alpha"
    assert row["week_id"] == "week_001" and row["quiz_result"] == result_label
    assert row["quiz_markdown"] == first["quiz_markdown"] and row["learner_answers"] == "Original answers"


def test_changed_identity_or_content_is_rejected_before_evaluation(days, monkeypatch):
    root, weeks = days
    generated = generate_day_quiz_service(identity=quiz_day_identity(resolve_quiz_day(weeks, "alpha")[0]), model="mock", base_dir=root)
    monkeypatch.setattr(tools, "evaluate_micro_quiz", lambda **kw: pytest.fail("Invalid quiz must not be evaluated"))
    with pytest.raises(ValueError, match="content changed"):
        evaluate_day_quiz_service(binding=generated["binding"], quiz_markdown="Different quiz", learner_answers="answer", model="mock", base_dir=root)
    with pytest.raises(ValueError, match="unavailable"):
        evaluate_day_quiz_service(binding={**generated["binding"], "roadmap_id": "beta"}, quiz_markdown=generated["quiz_markdown"], learner_answers="answer", model="mock", base_dir=root)
    saved, _ = read_progress(root)
    assert all(not d["quiz_result"] for w in saved for d in w["days"])


def test_answers_edited_after_evaluation_are_preserved_on_context_change():
    state = {"quiz_markdown": QUIZ, "quiz_eval": {"move_on_decision": "MOVE_ON"},
             "quiz_submitted_answers": {"quiz_answer_1": "Submitted"}, "quiz_answer_1": "New unsent edit"}
    preserve_quiz_draft(state)
    assert state["saved_quiz_drafts"][0]["quiz_answer_1"] == "New unsent edit"
