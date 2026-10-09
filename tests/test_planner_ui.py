"""Planner routing and saved-plan selection through real Streamlit reruns."""
import json
import os
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest
from src.core.services import planner_service
from src.agent import tools
from src.agent.learner_setup import make_learner_setup

APP = Path(__file__).resolve().parents[1] / "app.py"
REAL_PLANNER_SERVICE = planner_service.run_weekly_planner_service


def widget(at, kind, label):
    return next(item for item in getattr(at, kind) if item.label == label)


@pytest.fixture
def roadmap_ui(ui):
    at, calls, root = ui
    library = root / "docs" / "learning_units"
    for name in ("alpha_day.md", "alpha_week.md", "alpha_review.md", "beta_day.md"):
        (library / name).write_text(f"# {name}\n\n## Lesson\nOriginal lesson content")
    progress = root / "data" / "learning_progress.json"
    progress.parent.mkdir()
    progress.write_text(json.dumps({"roadmap_id": "unsafe_legacy_owner", "weeks": [
        {"roadmap_id": "alpha", "week_id": "week_001", "week_number_global": 1,
         "learning_unit_path": "docs/learning_units/alpha_week.md", "goal": "Alpha foundations",
         "days": [
             {"day_id": "day_001", "day_number": 1, "topic": "Alpha passed topic", "quiz_result": "PASS", "learning_unit_path": "docs/learning_units/alpha_day.md"},
             {"day_id": "day_002", "day_number": 2, "topic": "Alpha failed topic", "quiz_result": "FAIL"},
             {"day_id": "day_003", "day_number": 3, "topic": "Alpha future topic", "quiz_result": ""},
             {"day_id": "day_004", "day_number": 4, "topic": "Review alpha", "quiz_result": "", "is_review": True, "review_of_day_id": "day_002", "learning_unit_path": "docs/learning_units/alpha_review.md"},
         ]},
        {"roadmap_id": "beta", "week_id": "week_002", "week_number_global": 2,
         "days": [{"day_id": "day_005", "day_number": 1, "topic": "Beta only topic", "quiz_result": "PASS", "learning_unit_path": "docs/learning_units/beta_day.md"}]},
    ]}))
    at.radio(key="planner_route").set_value("Use an existing roadmap").run()
    at.selectbox(key="planner_saved_roadmap").set_value("alpha").run()
    assert not at.exception
    return at, calls, root


def test_progress_and_library_are_isolated_before_generation(roadmap_ui):
    at, calls, root = roadmap_ui
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    planner_text = "\n".join(item.value for item in at.tabs[0].markdown)
    assert any(item.value == "Alpha learning" for item in at.tabs[0].subheader)
    assert "Alpha passed topic" in planner_text and "Needs review" in planner_text
    assert "Beta only topic" not in planner_text
    assert at.tabs[0].metric[0].value == "1 of 3"
    assert at.tabs[0].metric[1].value == "0 of 1"
    assert at.session_state["active_roadmap_id"] == "alpha"
    choices = at.selectbox(key="learning_unit_select").options
    assert len(choices) == 3 and not any("Beta" in value or "existing.md" in value for value in choices)
    widget(at, "button", "Continue Learning — Week 1, Day 4").click().run()
    assert not at.exception
    assert at.selectbox(key="learning_unit_select").value == "alpha_review.md"
    assert at.session_state["workspace_tab"] == "Learning Library"
    assert calls == []
    assert {p: p.read_bytes() for p in root.rglob("*") if p.is_file()} == before


def test_switching_roadmaps_clears_preview_quiz_and_library_context(roadmap_ui):
    at, calls, root = roadmap_ui
    at.session_state["planner_plan_md"] = "Stale Alpha preview"
    at.session_state["planner_linkedin_md"] = "Stale Alpha draft"
    at.session_state["quiz_markdown"] = "Stale Alpha quiz"
    at.session_state["quiz_answer_1"] = "Stale Alpha answer"
    at.selectbox(key="planner_saved_roadmap").set_value("beta").run()
    assert not at.exception
    assert at.session_state["active_roadmap_id"] == "beta"
    assert at.session_state["quiz_roadmap_id"] == "beta"
    # A completed roadmap has no recommended day; historical browsing is explicit.
    assert at.selectbox(key="learning_unit_select").value is None
    assert len(at.selectbox(key="learning_unit_select").options) == 1
    text = "\n".join(item.value for item in at.tabs[0].markdown)
    assert any(item.value == "Beta learning" for item in at.tabs[0].subheader)
    assert "Alpha" not in text
    assert at.tabs[0].metric[0].value == "1 of 1"
    assert not at.session_state.filtered_state.get("planner_plan_md")
    assert not at.session_state.filtered_state.get("quiz_markdown")
    assert "quiz_answer_1" not in at.session_state.filtered_state
    assert calls == []


def test_library_headers_follow_selected_unit_and_preserve_week_scope(roadmap_ui):
    at, calls, root = roadmap_ui
    unit = root / "docs" / "learning_units" / "alpha_day.md"
    before = unit.read_bytes()
    at.selectbox(key="learning_unit_select").set_value("alpha_day.md").run()
    library = at.tabs[4]
    assert any(c.value == "Week 1 · Day 1" for c in library.caption)
    assert any(m.value == "**Topic:** Alpha passed topic" for m in library.markdown)
    assert any(m.value == "**Status:** Completed" for m in library.markdown)
    assert unit.read_bytes() == before
    at.selectbox(key="learning_unit_select").set_value("alpha_week.md").run()
    assert any(c.value == "Week 1 · Week overview" for c in at.tabs[4].caption)
    assert not any("Day " in c.value for c in at.tabs[4].caption)
    at.radio(key="planner_route").set_value("Start a new learning goal").run()
    at.selectbox(key="learning_unit_select").set_value("existing.md").run()
    assert any("context unavailable" in c.value for c in at.tabs[4].caption)
    assert not at.exception and calls == []


def test_unknown_progress_does_not_fabricate_completion(ui):
    at, calls, root = ui
    path = root / "data" / "learning_progress.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"roadmap_id": "alpha", "weeks": [
        {"goal": "Alpha learning", "days": [{"status": "PASSED", "quiz_result": "PASS"}]},
    ]}))
    at.radio(key="planner_route").set_value("Use an existing roadmap").run()
    at.selectbox(key="planner_saved_roadmap").set_value("alpha").run()
    assert not at.exception
    assert any("Progress unavailable" in msg.value for msg in at.tabs[0].info)
    assert not at.tabs[0].metric
    assert not any(s.label == "Choose a learning unit" for s in at.tabs[4].selectbox)
    assert calls == []


def test_day_generation_opens_material_without_completing_day(roadmap_ui, monkeypatch):
    from src.agent.learning_progress_store import update_day_learning_unit_path
    at, calls, root = roadmap_ui
    path = root / "data" / "learning_progress.json"
    progress = json.loads(path.read_text())
    progress["weeks"][0]["days"][3]["learning_unit_path"] = ""
    path.write_text(json.dumps(progress))
    generated = []

    def generate(**kwargs):
        generated.append(kwargs)
        relative = "docs/learning_units/generated_review.md"
        (root / relative).write_text("# Review\n\n## Lesson\nReview content")
        update_day_learning_unit_path(path, kwargs["day_id"], relative)
        return {"learning_unit_path": relative}

    monkeypatch.setattr(tools, "tool_generate_learning_unit_for_day", generate)
    at.run()
    widget(at, "button", "Generate learning unit — Week 1, Day 4").click().run()
    assert not at.exception
    assert generated[0]["day_id"] == "day_004"
    assert at.selectbox(key="learning_unit_select").value == "generated_review.md"
    assert at.tabs[0].metric[0].value == "1 of 3"
    assert at.tabs[0].metric[1].value == "0 of 1"
    assert json.loads(path.read_text())["weeks"][0]["days"][3]["quiz_result"] == ""
    assert calls == []


@pytest.fixture
def quiz_day_ui(roadmap_ui, monkeypatch):
    at, calls, root = roadmap_ui
    path = root / "data" / "learning_progress.json"
    progress = json.loads(path.read_text())
    progress["weeks"][0]["days"] = progress["weeks"][0]["days"][:3]
    for day in progress["weeks"][0]["days"]:
        day["quiz_result"] = ""
    progress["weeks"][0]["days"][1]["learning_unit_path"] = "docs/learning_units/alpha_day2.md"
    path.write_text(json.dumps(progress))
    (root / "docs" / "learning_units" / "alpha_day2.md").write_text("# Day two\n\n## Lesson\nDAY TWO SAVED MATERIAL")
    generated = []
    quiz = "<<QUIZ>>\nDay quiz\nQ1) Explain this day's concept.\n<<ANSWER_KEY>>\nQ1: Explain the concept.\n<<RUBRIC>>\nBe accurate."
    monkeypatch.setattr(tools, "call_llm", lambda **kw: generated.append(kw) or quiz)
    monkeypatch.setattr(tools, "tool_select_quiz_tasks", lambda **kw: pytest.fail("Linked quizzes must omit roadmap-wide task filtering"))
    at.run()
    assert not at.exception
    return at, generated, root


def test_quiz_defaults_to_recommended_day_and_explicit_library_selection_overrides(quiz_day_ui):
    at, generated, root = quiz_day_ui
    topic = widget(at, "text_input", "Topic")
    assert topic.value == "Alpha passed topic" and topic.disabled
    assert any(c.value == "Week 1 · Day 1" for c in at.tabs[3].caption)
    at.selectbox(key="learning_unit_select").set_value("alpha_day2.md").run()
    assert widget(at, "text_input", "Topic").value == "Alpha failed topic"
    assert any(c.value == "Week 1 · Day 2" for c in at.tabs[3].caption)
    at.checkbox(key="quiz_use_tasks").check().run()
    widget(at, "button", "Generate quiz for Day 2").click().run()
    assert not at.exception
    assert "Day ID: day_002" in generated[0]["user_prompt"]
    assert "DAY TWO SAVED MATERIAL" in generated[0]["user_prompt"]
    assert at.session_state["quiz_binding"]["day_id"] == "day_002"
    assert "quiz_task_ids" not in at.session_state.filtered_state
    assert any("Task filtering is omitted" in c.value for c in at.tabs[3].caption)


@pytest.mark.parametrize("decision,label,count", [("MOVE_ON", "PASS", "1 of 3"), ("REPEAT", "FAIL", "0 of 3")])
def test_linked_quiz_evaluation_refreshes_progress_for_selected_day_only(quiz_day_ui, monkeypatch, decision, label, count):
    at, generated, root = quiz_day_ui
    at.selectbox(key="learning_unit_select").set_value("alpha_day2.md").run()
    widget(at, "button", "Generate quiz for Day 2").click().run()
    original_binding = dict(at.session_state["quiz_binding"])
    at.text_area(key="quiz_answer_1").set_value("My answer for Day 2").run()
    monkeypatch.setattr(tools, "evaluate_micro_quiz", lambda **kw: {
        "move_on_decision": decision, "eval_block": "Evaluation of Day 2", "score": 8,
    })
    widget(at, "button", "Submit answers for evaluation").click().run()
    assert not at.exception
    assert at.tabs[0].metric[0].value == count
    assert at.session_state["quiz_binding"] == original_binding
    progress = json.loads((root / "data" / "learning_progress.json").read_text())
    assert progress["weeks"][0]["days"][1]["quiz_result"] == label
    assert progress["weeks"][0]["days"][0]["quiz_result"] == ""
    assert progress["weeks"][1]["days"][0]["quiz_result"] == "PASS"
    history = json.loads((root / "data" / "quiz_results.jsonl").read_text().splitlines()[-1])
    assert history["day_id"] == "day_002" and history["roadmap_id"] == "alpha"
    assert history["learner_answers"] == "Q1: My answer for Day 2"


def test_roadmap_switch_invalidates_quiz_and_preserves_unsent_answers(quiz_day_ui, monkeypatch):
    at, generated, root = quiz_day_ui
    widget(at, "button", "Generate quiz for Day 1").click().run()
    binding = dict(at.session_state["quiz_binding"])
    at.text_area(key="quiz_answer_1").set_value("Unsent Day 1 answer").run()
    at.selectbox(key="planner_saved_roadmap").set_value("beta").run()
    assert not at.exception
    assert not at.session_state.filtered_state.get("quiz_binding")
    assert not at.session_state.filtered_state.get("quiz_markdown")
    draft = at.session_state["saved_quiz_drafts"][-1]
    assert draft["quiz_binding"] == binding
    assert draft["quiz_answer_1"] == "Unsent Day 1 answer"
    assert any("previous quiz and unsent answers were preserved" in w.value for w in at.tabs[3].warning)
    monkeypatch.setattr(tools, "evaluate_micro_quiz", lambda **kw: pytest.fail("A stale quiz must not be submitted"))
    widget(at, "button", "Submit answers for evaluation").click().run()
    assert any("Generate or paste a quiz first" in w.value for w in at.tabs[3].warning)
    assert json.loads((root / "data" / "learning_progress.json").read_text())["weeks"][0]["days"][0]["quiz_result"] == ""


def test_day_switch_invalidates_quiz_and_preserves_original_draft(quiz_day_ui):
    at, generated, root = quiz_day_ui
    widget(at, "button", "Generate quiz for Day 1").click().run()
    at.text_area(key="quiz_answer_1").set_value("Unsent first-day answer").run()
    at.selectbox(key="learning_unit_select").set_value("alpha_day2.md").run()
    assert not at.exception
    assert widget(at, "text_input", "Topic").value == "Alpha failed topic"
    assert not at.session_state.filtered_state.get("quiz_markdown")
    assert at.session_state["saved_quiz_drafts"][-1]["quiz_binding"]["day_id"] == "day_001"
    assert at.session_state["saved_quiz_drafts"][-1]["quiz_answer_1"] == "Unsent first-day answer"


def test_regenerated_quiz_does_not_retain_previous_evaluation(quiz_day_ui, monkeypatch):
    at, generated, root = quiz_day_ui
    widget(at, "button", "Generate quiz for Day 1").click().run()
    at.text_area(key="quiz_answer_1").set_value("First attempt").run()
    monkeypatch.setattr(tools, "evaluate_micro_quiz", lambda **kw: {"move_on_decision": "MOVE_ON", "eval_block": "Passed"})
    widget(at, "button", "Submit answers for evaluation").click().run()
    first_id = at.session_state["quiz_binding"]["quiz_id"]
    widget(at, "button", "Generate quiz for Day 1").click().run()
    assert not at.exception
    assert at.session_state["quiz_binding"]["quiz_id"] != first_id
    assert "quiz_eval" not in at.session_state.filtered_state
    assert "quiz_submitted_answers" not in at.session_state.filtered_state


def test_explicit_incomplete_day_blocks_generation_instead_of_falling_back(quiz_day_ui):
    at, generated, root = quiz_day_ui
    path = root / "data" / "learning_progress.json"
    data = json.loads(path.read_text())
    data["weeks"][0]["days"][1]["topic"] = ""
    path.write_text(json.dumps(data))
    at.run()
    at.selectbox(key="learning_unit_select").set_value("alpha_day2.md").run()
    assert not at.exception
    assert any("incomplete or ambiguous" in w.value for w in at.tabs[3].warning)
    assert widget(at, "text_input", "Topic").value == ""
    assert widget(at, "button", "Generate quiz").disabled
    assert not generated


def test_standalone_quiz_keeps_editable_topic_and_does_not_update_days(quiz_day_ui, monkeypatch):
    from src.core.services import quiz_service
    at, generated, root = quiz_day_ui
    at.radio(key="planner_route").set_value("Start a new learning goal").run()
    assert not widget(at, "text_input", "Topic").disabled
    before = (root / "data" / "learning_progress.json").read_bytes()
    captured = []
    quiz = "<<QUIZ>>\nStandalone quiz\nQ1) Explain your topic.\n<<ANSWER_KEY>>\nQ1: Explanation."

    def standalone(**kw):
        captured.append(kw)
        return {"quiz_markdown": quiz, "quiz_path": "standalone.md"}

    monkeypatch.setattr(quiz_service, "generate_quiz_service", standalone)
    monkeypatch.setattr(quiz_service, "evaluate_quiz_service", lambda **kw: {"eval_block": "Standalone evaluation", "move_on_decision": "MOVE_ON"})
    widget(at, "text_input", "Topic").set_value("My standalone topic").run()
    widget(at, "button", "Generate quiz").click().run()
    at.text_area(key="quiz_answer_1").set_value("My standalone answer").run()
    widget(at, "button", "Submit answers for evaluation").click().run()
    assert not at.exception
    assert captured[0]["topic"] == "My standalone topic"
    assert not at.session_state.filtered_state.get("quiz_binding")
    assert (root / "data" / "learning_progress.json").read_bytes() == before


@pytest.fixture
def ui(tmp_path, monkeypatch):
    roadmaps = tmp_path / "roadmaps"
    roadmaps.mkdir()
    for identifier, title in [("alpha", "Alpha learning"), ("beta", "Beta learning")]:
        (roadmaps / f"{identifier}_roadmap.json").write_text(json.dumps({"topic": title, "phases": [{"title": "Basics"}], "learner_setup": make_learner_setup(goal=title, background="", preferences="", hours_per_week=2.0, max_session_minutes=30, learning_intensity="medium")}))
    plans = tmp_path / "weekly_plans"
    plans.mkdir()
    old = plans / "old.md"
    old.write_text("# Historical plan")
    library = tmp_path / "docs" / "learning_units"
    library.mkdir(parents=True)
    (library / "existing.md").write_text("# Existing unit\n\n## Topic\nSaved learning content")
    calls = []

    def generate(**kwargs):
        calls.append(kwargs)
        plan = plans / "generated.md"
        plan.write_text("# Generated plan")
        # Deliberately make another file newer than the returned plan.
        os.utime(plan, (1, 1))
        return {"result": {"plan_path": str(plan)}, "plan_md": "# Generated plan", "linkedin_md": "Draft"}

    monkeypatch.setattr(planner_service, "run_weekly_planner_service", generate)
    source = APP.read_text().replace('BASE_DIR = Path(__file__).resolve().parent', f'BASE_DIR = Path({str(tmp_path)!r})')
    at = AppTest.from_string(source).run()
    assert not at.exception
    return at, calls, tmp_path


def test_routes_browsing_and_exact_generated_plan(ui):
    at, calls, root = ui
    saved_content = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    at.session_state["active_roadmap_id"] = "obsolete"
    at.session_state["planner_roadmap_id"] = "obsolete"
    at.radio(key="planner_route").set_value("Use an existing roadmap").run()
    assert widget(at, "button", "Generate plan").disabled
    assert "Alpha learning" in at.selectbox(key="planner_saved_roadmap").options[0]
    at.selectbox(key="planner_saved_roadmap").set_value("alpha").run()
    assert calls == []
    assert tools.tool_load_learning_roadmap(goal="unrelated", base_dir=root, roadmap_id="alpha")["roadmap"]["topic"] == "Alpha learning"
    at.selectbox(key="roadmaps_select").set_value(root / "roadmaps" / "beta_roadmap.json").run()
    assert at.selectbox(key="planner_saved_roadmap").value == "alpha"
    assert not any(b.label == "Set as active roadmap" for b in at.button)
    assert calls == []
    assert {p: p.read_bytes() for p in root.rglob("*") if p.is_file()} == saved_content
    widget(at, "button", "Generate plan").click().run()
    assert calls[-1]["roadmap_id"] == "alpha"
    assert at.selectbox(key="weekly_plans_select").value == root / "weekly_plans" / "generated.md"
    at.selectbox(key="weekly_plans_select").set_value(root / "weekly_plans" / "old.md").run()
    assert at.selectbox(key="weekly_plans_select").value.name == "old.md"
    assert len(calls) == 1
    at.radio(key="planner_route").set_value("Start a new learning goal").run()
    widget(at, "button", "Generate plan").click().run()
    assert calls[-1]["roadmap_id"] is None
    assert not at.exception
    assert widget(at, "button", "Generate quiz")
    assert widget(at, "selectbox", "Choose a learning unit").value == "existing.md"
    widget(at, "button", "Refresh library").click().run()
    assert not at.exception
    assert any(t.label == "Learning Library" for t in at.tabs)


@pytest.mark.parametrize("failure", ["exception", "service_failure", "missing_file"])
def test_failed_generation_preserves_selection_and_preview_then_retry(ui, monkeypatch, failure):
    at, calls, root = ui
    widget(at, "button", "Generate plan").click().run()
    working_path = root / "weekly_plans" / "generated.md"
    assert at.selectbox(key="weekly_plans_select").value == working_path
    previous = {key: at.session_state[key] for key in (
        "planner_result", "planner_plan_md", "planner_linkedin_md",
    )}
    saved_files = {p: p.read_bytes() for p in (root / "weekly_plans").glob("*.md")}
    backend_calls = []

    def fail(**kwargs):
        backend_calls.append(kwargs)
        if failure == "exception":
            raise RuntimeError("Provider unavailable")
        if failure == "service_failure":
            # Actual ReAct result shape on controller parse failure, no outputs saved.
            return planner_service.react_agent._safe_final_result(
                {"weekly_plan_path": ""}, final_reason="parse_error",
            )
        return {"plan_path": str(root / "weekly_plans" / "missing.md")}

    monkeypatch.setattr(planner_service, "run_weekly_planner_service", REAL_PLANNER_SERVICE)
    monkeypatch.setattr(planner_service.weekly_planner, "generate_and_save_week", fail)
    monkeypatch.setattr(planner_service.react_agent, "run_weekly_planner_agent_react", fail)
    if failure == "service_failure":
        at.checkbox(key="planner_use_agent").check().run()
    widget(at, "button", "Generate plan").click().run()
    assert len(backend_calls) == 1
    assert not at.exception
    expected_error = {
        "exception": "Provider unavailable",
        "service_failure": "Planner returned no saved weekly plan",
        "missing_file": "generated weekly plan file is missing",
    }[failure]
    assert any("Failed to generate plan" in msg.value and expected_error in msg.value for msg in at.error)
    if failure == "service_failure":
        assert "parse_error" in at.error[0].value
    assert at.selectbox(key="weekly_plans_select").value == working_path
    assert working_path.is_file()
    for key, value in previous.items():
        assert at.session_state[key] == value
    assert any(msg.value == "# Generated plan" for msg in at.markdown)
    assert {p: p.read_bytes() for p in (root / "weekly_plans").glob("*.md")} == saved_files
    assert not at.success

    def retry(**kwargs):
        backend_calls.append(kwargs)
        path = root / "weekly_plans" / "retry.md"
        path.write_text("# Retry plan")
        if failure == "service_failure":
            return planner_service.react_agent._safe_final_result(
                {"weekly_plan_path": str(path)}, final_reason="success",
            )
        return {"plan_path": path, "raw_markdown": "# Retry plan"}

    monkeypatch.setattr(planner_service.weekly_planner, "generate_and_save_week", retry)
    monkeypatch.setattr(planner_service.react_agent, "run_weekly_planner_agent_react", retry)
    widget(at, "button", "Generate plan").click().run()
    assert len(backend_calls) == 2
    assert not at.exception and not at.error
    assert at.selectbox(key="weekly_plans_select").value == root / "weekly_plans" / "retry.md"
    assert at.session_state["planner_result"]["plan_path"] == str(root / "weekly_plans" / "retry.md")
    assert "# Retry plan" in at.session_state["planner_plan_md"]
    assert any(msg.value == "# Retry plan" for msg in at.markdown)
    assert any(msg.value == "Saved" for msg in at.success)
    assert working_path.read_bytes() == saved_files[working_path]


def test_missing_selections_and_empty_roadmaps(ui):
    at, calls, root = ui
    at.radio(key="planner_route").set_value("Use an existing roadmap").run()
    at.selectbox(key="planner_saved_roadmap").set_value("alpha").run()
    (root / "roadmaps" / "alpha_roadmap.json").unlink()
    at.run()
    assert at.selectbox(key="planner_saved_roadmap").value is None
    assert widget(at, "button", "Generate plan").disabled
    (root / "roadmaps" / "beta_roadmap.json").unlink()
    (root / "roadmaps" / "invalid_roadmap.json").write_text("broken json")
    at.run()
    assert any("No saved roadmaps available" in msg.value for msg in at.info)
    (root / "weekly_plans" / "other.md").write_text("# Other plan")
    (root / "weekly_plans" / "old.md").unlink()
    at.run()
    assert not at.exception
    assert at.selectbox(key="weekly_plans_select").value.name == "other.md"
    assert any("previously selected weekly plan is no longer available" in msg.value for msg in at.warning)
    assert any(msg.value == "# Other plan" for msg in at.markdown)
    assert calls == []
    (root / "weekly_plans" / "other.md").unlink()
    at.run()
    assert not at.exception
    assert not any(item.label == "Choose a weekly plan" for item in at.selectbox)
    assert any("No weekly plans found" in msg.value for msg in at.info)
    assert calls == []


def test_empty_roadmap_list_guides_new_goal_without_generation(ui):
    at, calls, root = ui
    for path in (root / "roadmaps").glob("*.json"):
        path.unlink()  # Temporary fixture files only.
    at.radio(key="planner_route").set_value("Use an existing roadmap").run()
    assert not at.exception
    assert at.selectbox(key="planner_saved_roadmap").options == []
    assert at.selectbox(key="planner_saved_roadmap").value is None
    assert widget(at, "button", "Generate plan").disabled
    assert any("Start a new learning goal" in msg.value and "create one" in msg.value for msg in at.info)
    assert at.selectbox(key="weekly_plans_select").value.name == "old.md"
    assert calls == []
    at.radio(key="planner_route").set_value("Start a new learning goal").run()
    assert not widget(at, "button", "Generate plan").disabled
    assert calls == []


@pytest.mark.parametrize("agent", [False, True])
def test_service_contract_normalizes_path_and_passes_roadmap(tmp_path, monkeypatch, agent):
    path = tmp_path / "weekly_plans" / "exact.md"
    path.parent.mkdir()
    path.write_text("# Exact saved plan")
    roadmaps = tmp_path / "roadmaps"
    roadmaps.mkdir()
    (roadmaps / "alpha_roadmap.json").write_text(json.dumps({"learner_setup": make_learner_setup(
        goal="Goal", background="", preferences="Practical", hours_per_week=2,
        max_session_minutes=30, learning_intensity="medium",
    )}))
    calls = []

    def backend(**kwargs):
        calls.append(kwargs)
        return {"weekly_plan_path" if agent else "plan_path": path, "raw_markdown": "# Exact saved plan"}

    monkeypatch.setattr(planner_service.react_agent, "run_weekly_planner_agent_react", backend)
    monkeypatch.setattr(planner_service.weekly_planner, "generate_and_save_week", backend)
    output = planner_service.run_weekly_planner_service(
        goal="Goal", hours_per_week=2, max_session_minutes=30,
        preferences_text="Practical", intensity="medium", background="",
        roadmap_id="alpha", force_regenerate_roadmap=False, model="test",
        use_agent_loop=agent, mock_actions_path=None, enable_critic=False, base_dir=tmp_path,
    )
    assert output["result"]["plan_path"] == str(path)
    assert (calls[0]["preferences"]["roadmap_id"] if agent else calls[0]["roadmap_id"]) == "alpha"


def test_saved_setup_restores_in_fresh_session_and_roadmaps_stay_separate(ui):
    at, calls, root = ui
    setups = {
        "alpha": make_learner_setup(goal="Goal A", background="Background A", preferences="Preferences A",
                                   hours_per_week=3.5, max_session_minutes=45, learning_intensity="hardcore"),
        "beta": make_learner_setup(goal="Goal B", background="", preferences="",
                                  hours_per_week=1.0, max_session_minutes=10, learning_intensity="light"),
    }
    for identifier, setup in setups.items():
        path = root / "roadmaps" / f"{identifier}_roadmap.json"
        data = json.loads(path.read_text())
        data["learner_setup"] = setup
        path.write_text(json.dumps(data))
    progress = root / "data" / "learning_progress.json"
    progress.parent.mkdir()
    progress.write_text('{"roadmap_id":"untouched","weeks":[]}')
    snapshot = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    # New Streamlit session: only disk persists, not the previous session state.
    source = APP.read_text().replace('BASE_DIR = Path(__file__).resolve().parent', f'BASE_DIR = Path({str(root)!r})')
    at = AppTest.from_string(source).run()
    widget(at, "text_input", "Goal / focus").set_value("Editable draft").run()
    widget(at, "text_area", "Background / constraints (optional)").set_value("Draft background").run()
    widget(at, "slider", "Time available per week (hours)").set_value(2.5).run()
    at.radio(key="planner_route").set_value("Use an existing roadmap").run()
    for identifier in ("alpha", "beta", "alpha"):
        at.selectbox(key="planner_saved_roadmap").set_value(identifier).run()
        assert not at.exception
        setup = setups[identifier]
        for kind, label, field in (
            ("text_input", "Goal / focus", "goal"),
            ("text_area", "Background / constraints (optional)", "background"),
            ("text_area", "Preferences / constraints", "preferences"),
            ("slider", "Time available per week (hours)", "hours_per_week"),
            ("selectbox", "Max session length (minutes)", "max_session_minutes"),
            ("selectbox", "Learning intensity", "learning_intensity"),
        ):
            item = widget(at, kind, label)
            assert item.value == setup[field]
            assert item.disabled
        at.run()
        assert not at.exception
    assert calls == []
    assert {p: p.read_bytes() for p in root.rglob("*") if p.is_file()} == snapshot
    widget(at, "button", "Generate plan").click().run()
    assert calls[-1]["goal"] == "Goal A"
    assert calls[-1]["background"] == "Background A"
    assert calls[-1]["preferences_text"] == "Preferences A"
    assert calls[-1]["hours_per_week"] == 3.5
    assert calls[-1]["max_session_minutes"] == 45
    assert calls[-1]["intensity"] == "hardcore"
    assert calls[-1]["roadmap_id"] == "alpha"
    assert not calls[-1]["force_regenerate_roadmap"]
    at.radio(key="planner_route").set_value("Start a new learning goal").run()
    assert widget(at, "text_input", "Goal / focus").value == "Editable draft"
    assert widget(at, "text_area", "Background / constraints (optional)").value == "Draft background"
    assert widget(at, "slider", "Time available per week (hours)").value == 2.5
    for kind, label in (("text_input", "Goal / focus"), ("text_area", "Background / constraints (optional)"),
                        ("text_area", "Preferences / constraints"), ("slider", "Time available per week (hours)"),
                        ("selectbox", "Max session length (minutes)"), ("selectbox", "Learning intensity")):
        assert not widget(at, kind, label).disabled
    widget(at, "button", "Generate plan").click().run()
    assert calls[-1]["roadmap_id"] is None
    assert calls[-1]["goal"] == "Editable draft"
    assert not at.exception


@pytest.mark.parametrize("metadata", [None, {}, {"goal": "Incomplete"}, {
    "goal": "Goal", "background": "", "preferences": "", "hours_per_week": 2,
    "max_session_minutes": 30, "learning_intensity": "invalid",
}])
def test_invalid_saved_setup_blocks_ui_generation(ui, metadata):
    at, calls, root = ui
    path = root / "roadmaps" / "alpha_roadmap.json"
    data = json.loads(path.read_text())
    data["learner_setup"] = metadata
    path.write_text(json.dumps(data))
    original = path.read_bytes()
    at.radio(key="planner_route").set_value("Use an existing roadmap").run()
    at.selectbox(key="planner_saved_roadmap").set_value("alpha").run()
    assert not at.exception
    assert any("learner_setup" in error.value for error in at.error)
    assert widget(at, "button", "Generate plan").disabled
    assert widget(at, "text_input", "Goal / focus").disabled
    at.run()
    assert calls == []
    assert path.read_bytes() == original


def test_metadata_save_failure_ui_does_not_announce_success(ui, monkeypatch):
    from test_roadmap_learner_setup import CURRICULUM
    at, calls, root = ui
    widget(at, "button", "Generate plan").click().run()
    previous = at.session_state["planner_result"]
    monkeypatch.setattr(planner_service, "run_weekly_planner_service", REAL_PLANNER_SERVICE)
    monkeypatch.setattr(tools, "call_llm", lambda **kw: json.dumps(CURRICULUM))

    def backend(**kw):
        return tools.tool_generate_learning_roadmap(
            goal=kw["goal"], background=kw["background"], target_level=kw["target_level"],
            roadmap_id=kw["roadmap_id"], base_dir=kw["base_dir"], model=kw["model"], learner_setup=kw["learner_setup"],
        )

    monkeypatch.setattr(planner_service.weekly_planner, "generate_and_save_week", backend)
    write = Path.write_text

    def fail(path, *args, **kw):
        if path.parent == root / "roadmaps" and path.suffix == ".json":
            raise OSError("Simulated metadata disk failure")
        return write(path, *args, **kw)

    monkeypatch.setattr(Path, "write_text", fail)
    widget(at, "button", "Generate plan").click().run()
    assert not at.exception
    assert any("Failed to save roadmap with required learner_setup" in error.value for error in at.error)
    assert not at.success
    assert at.session_state["planner_result"] == previous
    assert at.selectbox(key="weekly_plans_select").value == root / "weekly_plans" / "generated.md"


def test_new_goal_ui_persists_submitted_setup_and_fresh_session_restores(ui, monkeypatch):
    from test_roadmap_learner_setup import CURRICULUM
    at, calls, root = ui
    submitted = make_learner_setup(goal="Distinct UI goal", background="UI background", preferences="UI constraints",
                                   hours_per_week=4.5, max_session_minutes=60, learning_intensity="hardcore")
    monkeypatch.setattr(planner_service, "run_weekly_planner_service", REAL_PLANNER_SERVICE)
    monkeypatch.setattr(tools, "call_llm", lambda **kw: json.dumps(CURRICULUM))

    def backend(**kw):
        roadmap = tools.tool_generate_learning_roadmap(
            goal=kw["goal"], background=kw["background"], target_level=kw["target_level"],
            roadmap_id=kw["roadmap_id"], base_dir=kw["base_dir"], model=kw["model"], learner_setup=kw["learner_setup"],
        )
        plan = root / "weekly_plans" / "fresh.md"
        plan.write_text("# Fresh UI plan")
        return {"plan_path": plan, "roadmap_path": roadmap["path"], "raw_markdown": "# Fresh UI plan"}

    monkeypatch.setattr(planner_service.weekly_planner, "generate_and_save_week", backend)
    widget(at, "text_input", "Goal / focus").set_value(submitted["goal"])
    widget(at, "text_area", "Background / constraints (optional)").set_value(submitted["background"])
    widget(at, "text_area", "Preferences / constraints").set_value(submitted["preferences"])
    widget(at, "slider", "Time available per week (hours)").set_value(submitted["hours_per_week"])
    widget(at, "selectbox", "Max session length (minutes)").set_value(submitted["max_session_minutes"])
    widget(at, "selectbox", "Learning intensity").set_value(submitted["learning_intensity"])
    widget(at, "button", "Generate plan").click().run()
    assert not at.exception and not at.error
    assert any(msg.value == "Saved" for msg in at.success)
    path = root / "roadmaps" / "distinct_ui_goal_roadmap.json"
    assert json.loads(path.read_text())["learner_setup"] == submitted
    original = path.read_bytes()
    source = APP.read_text().replace('BASE_DIR = Path(__file__).resolve().parent', f'BASE_DIR = Path({str(root)!r})')
    restarted = AppTest.from_string(source).run()
    restarted.radio(key="planner_route").set_value("Use an existing roadmap").run()
    restarted.selectbox(key="planner_saved_roadmap").set_value("distinct_ui_goal").run()
    assert not restarted.exception and not restarted.error
    for key, field in (("existing_planner_goal", "goal"), ("existing_planner_background", "background"),
                       ("existing_planner_preferences", "preferences"), ("existing_planner_hours", "hours_per_week"),
                       ("existing_planner_max_session", "max_session_minutes"), ("existing_planner_intensity", "learning_intensity")):
        assert restarted.session_state[key] == submitted[field]
    assert widget(restarted, "text_input", "Goal / focus").disabled
    assert path.read_bytes() == original
