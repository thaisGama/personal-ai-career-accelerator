"""Roadmap persistence through direct and ReAct routes without paid calls."""
import copy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.agent import tools, weekly_planner, react_agent
from src.agent.learner_setup import make_learner_setup, validate_learner_setup
from src.core.services.planner_service import run_weekly_planner_service

CURRICULUM = {
    "topic": "Model curriculum title", "target_level": "medium", "total_estimated_hours": 5,
    "estimated_weeks_at_hours_per_week": {"2": 3, "5": 1, "7": 1},
    "prerequisites": [], "completion_criteria": ["Explain topic"],
    "phases": [{"phase_id": "P1", "title": "Phase", "estimated_hours": 5, "outcomes": [],
                "milestones": [{"milestone_id": "M1.1", "title": "Milestone", "estimated_hours": 5,
                                "definition_of_done": [], "deliverables": [], "depth": "intro",
                                "suggested_practice": [], "resources": []}]}],
}
SETUP = make_learner_setup(goal="Distinct submitted goal", background="", preferences="",
                          hours_per_week=3.5, max_session_minutes=45, learning_intensity="hardcore")
PLAN = "# Week 1 Learning Plan\n\n- 🔥 **Day 1 (20 min): Topic** [phase:P1][milestone:M1.1]"


@pytest.fixture
def mocked_content(monkeypatch):
    curriculum = copy.deepcopy(CURRICULUM)
    curriculum["learner_setup"] = {"goal": "Ignore model-authored metadata"}
    monkeypatch.setattr(tools, "call_llm", lambda **kw: json.dumps(curriculum))
    # Tripwire against accidentally invoking real embeddings in these tests.
    monkeypatch.setattr(tools.LocalVectorStore, "embed", lambda *args: pytest.fail("Real embedding path invoked"))
    monkeypatch.setattr(tools.LocalVectorStore, "search", lambda *args, **kw: [])
    monkeypatch.setattr(react_agent, "tool_retrieve_memory", lambda **kw: {"memory_context": "", "audit": {}})
    monkeypatch.setattr(weekly_planner, "generate_weekly_plan_and_learning_unit", lambda **kw: {
        "plan_markdown": PLAN, "linkedin_markdown": "Draft", "memory_snippet": "", "learning_unit_md": "",
    })
    monkeypatch.setattr(react_agent, "tool_generate_weekly_plan", lambda **kw: {
        "weekly_plan_md": PLAN, "linkedin_post_md": "Draft", "memory_snippet": "", "learning_unit_md": "",
    })


def service(root, agent=False, **updates):
    inputs = dict(goal=SETUP["goal"], background=SETUP["background"], preferences_text=SETUP["preferences"],
                  hours_per_week=SETUP["hours_per_week"], max_session_minutes=SETUP["max_session_minutes"],
                  intensity=SETUP["learning_intensity"], roadmap_id=None, force_regenerate_roadmap=False,
                  model="test", use_agent_loop=agent, mock_actions_path=None, enable_critic=False, base_dir=root)
    if agent:
        actions = root / "actions.jsonl"
        actions.write_text("\n".join(json.dumps({"action": "tool", "tool_name": name, "args": {}}) for name in (
            "retrieve_memory", "load_learning_roadmap", "generate_learning_roadmap", "summarize_task_progress",
            "generate_weekly_plan", "upsert_tasks_from_plan", "save_outputs", "decide_next_task",
        )) + '\n{"action":"final","result":{}}\n')
        inputs["mock_actions_path"] = actions
    inputs.update(updates)
    return run_weekly_planner_service(**inputs)


@pytest.mark.parametrize("empty_optional", [False, True])
@pytest.mark.parametrize("agent,force", [(False, False), (False, True), (True, False), (True, True)])
def test_generation_routes_persist_exact_application_setup(tmp_path, mocked_content, agent, force, empty_optional):
    expected = dict(SETUP)
    if not empty_optional:
        expected.update(background="Experienced learner — practical", preferences="  Use distinctive constraints.  ")
    result = service(tmp_path, agent, force_regenerate_roadmap=force,
                     background=expected["background"], preferences_text=expected["preferences"])
    roadmap_path = tmp_path / "roadmaps" / "distinct_submitted_goal_roadmap.json"
    roadmap = json.loads(roadmap_path.read_text())
    assert roadmap["learner_setup"] == expected
    assert roadmap["topic"] == CURRICULUM["topic"]
    assert tools._validate_roadmap_schema(roadmap) == (True, [])
    markdown = roadmap_path.with_suffix(".md").read_text()
    assert "## Learner setup" in markdown
    assert "hours_per_week: 3.5" in markdown
    assert Path(result["result"]["plan_path"]).is_file()
    progress = json.loads((tmp_path / "data" / "learning_progress.json").read_text())
    week = progress["weeks"][-1]
    assert week["roadmap_id"] == "distinct_submitted_goal"
    assert (tmp_path / week["plan_path"]).resolve() == Path(result["result"]["plan_path"]).resolve()


@pytest.mark.parametrize("agent", [False, True])
def test_generation_routes_link_week_level_learning_material(tmp_path, mocked_content, monkeypatch, agent):
    content = {"plan_markdown": PLAN, "linkedin_markdown": "Draft", "memory_snippet": "",
               "learning_unit_md": "# Learning Unit: Week overview\n\n## Lesson\nOriginal content"}
    monkeypatch.setattr(weekly_planner, "generate_weekly_plan_and_learning_unit", lambda **kw: content)
    monkeypatch.setattr(react_agent, "tool_generate_weekly_plan", lambda **kw: {
        "weekly_plan_md": PLAN, "linkedin_post_md": "Draft", "memory_snippet": "",
        "learning_unit_md": content["learning_unit_md"],
    })
    result = service(tmp_path, agent)
    week = json.loads((tmp_path / "data" / "learning_progress.json").read_text())["weeks"][0]
    assert week["roadmap_id"] == "distinct_submitted_goal"
    assert (tmp_path / week["learning_unit_path"]).resolve() == Path(result["result"]["learning_unit_path"]).resolve()
    assert all(not day["learning_unit_path"] and not day["quiz_result"] for day in week["days"])


@pytest.mark.parametrize("agent", [False, True])
def test_existing_service_uses_persisted_setup_and_preserves_roadmap(tmp_path, monkeypatch, agent):
    root = tmp_path / "roadmaps"
    root.mkdir()
    path = root / "stable_roadmap.json"
    path.write_text(json.dumps(dict(CURRICULUM, learner_setup=SETUP)))
    before = path.read_bytes()
    received = []

    def backend(**kw):
        received.append(kw)
        return {"weekly_plan_path": ""}

    monkeypatch.setattr(react_agent, "run_weekly_planner_agent_react", backend)
    monkeypatch.setattr(weekly_planner, "generate_and_save_week", backend)
    service(tmp_path, agent, goal="Unrelated goal", background="Stale background", preferences_text="Stale preferences",
            hours_per_week=1.0, max_session_minutes=10, intensity="light", roadmap_id="stable", force_regenerate_roadmap=True)
    kw = received[0]
    assert kw["goal"] == SETUP["goal"]
    if agent:
        assert kw["hours_per_week"] == 3.5
        assert kw["preferences"]["learner_setup"] == SETUP
        assert kw["preferences"]["roadmap_id"] == "stable"
        assert not kw["preferences"]["force_regenerate_roadmap"]
    else:
        assert kw["time_per_week_hours"] == 3.5
        assert kw["learner_setup"] == SETUP
        assert kw["roadmap_id"] == "stable"
        assert not kw["force_regenerate_roadmap"]
    assert kw["max_session_minutes"] == 45
    assert path.read_bytes() == before


@pytest.mark.parametrize("field,value", [("goal", ""), ("background", None), ("preferences", 2),
    ("hours_per_week", True), ("hours_per_week", float("nan")), ("hours_per_week", 0),
    ("max_session_minutes", 22), ("max_session_minutes", True), ("learning_intensity", "unknown")])
def test_setup_validation_rejects_invalid_values(field, value):
    with pytest.raises(ValueError, match="learner_setup"):
        validate_learner_setup(dict(SETUP, **{field: value}))


def test_curriculum_validation_is_separate_from_required_setup():
    assert tools._validate_curriculum_schema(CURRICULUM) == (True, [])
    valid, errors = tools._validate_roadmap_schema(CURRICULUM)
    assert not valid and "learner_setup" in errors[0]
    assert validate_learner_setup(SETUP)["background"] == ""
    assert validate_learner_setup(SETUP)["preferences"] == ""


@pytest.mark.parametrize("agent", [False, True])
def test_incomplete_setup_blocks_service_before_backend(tmp_path, monkeypatch, agent):
    root = tmp_path / "roadmaps"
    root.mkdir()
    (root / "broken_roadmap.json").write_text(json.dumps({"learner_setup": {"goal": "Incomplete"}}))
    monkeypatch.setattr(react_agent, "run_weekly_planner_agent_react", lambda **kw: pytest.fail("Backend must not run"))
    monkeypatch.setattr(weekly_planner, "generate_and_save_week", lambda **kw: pytest.fail("Backend must not run"))
    with pytest.raises(ValueError, match="learner_setup.background"):
        service(tmp_path, agent, roadmap_id="broken")


@pytest.mark.parametrize("agent,suffix", [(False, ".json"), (True, ".json"), (False, ".md"), (True, ".md")])
def test_required_metadata_save_failure_propagates_without_plan(tmp_path, mocked_content, monkeypatch, agent, suffix):
    write = Path.write_text

    def fail(path, *args, **kw):
        if path.parent.name == "roadmaps" and path.suffix == suffix:
            raise OSError("Simulated disk failure")
        return write(path, *args, **kw)

    monkeypatch.setattr(Path, "write_text", fail)
    with pytest.raises(RuntimeError, match="Failed to save roadmap with required learner_setup"):
        service(tmp_path, agent)
    assert not list((tmp_path / "weekly_plans").glob("*.md"))
    assert not (tmp_path / "data" / "tasks.csv").exists()
