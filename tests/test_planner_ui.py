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

APP = Path(__file__).resolve().parents[1] / "app.py"
REAL_PLANNER_SERVICE = planner_service.run_weekly_planner_service


def widget(at, kind, label):
    return next(item for item in getattr(at, kind) if item.label == label)


@pytest.fixture
def ui(tmp_path, monkeypatch):
    roadmaps = tmp_path / "roadmaps"
    roadmaps.mkdir()
    for identifier, title in [("alpha", "Alpha learning"), ("beta", "Beta learning")]:
        (roadmaps / f"{identifier}_roadmap.json").write_text(json.dumps({"topic": title, "phases": [{"title": "Basics"}]}))
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
