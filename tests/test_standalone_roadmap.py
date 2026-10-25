"""Standalone generation and Streamlit reruns; no paid API calls."""

import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.agent import react_agent, tools, weekly_planner
from standalone_roadmap import service


CURRICULUM = {
    "topic": "IAM policies", "target_level": "medium", "total_estimated_hours": 5,
    "estimated_weeks_at_hours_per_week": {"2": 3, "5": 1, "7": 1},
    "prerequisites": [], "completion_criteria": ["Explain IAM policies"],
    "phases": [{"phase_id": "P1", "title": "Foundations", "estimated_hours": 5,
                "outcomes": ["Understand permissions"], "milestones": [{
                    "milestone_id": "M1.1", "title": "Policy evaluation",
                    "estimated_hours": 5, "definition_of_done": ["Explain deny precedence"],
                    "deliverables": [], "depth": "intro", "suggested_practice": [], "resources": [],
                }]}],
}
INPUTS = dict(goal="Learn IAM policies", background="Basic AWS",
              learning_purpose="topic_mastery", hours_per_week=3.5,
              learning_intensity="medium")
APP = str(Path(__file__).resolve().parents[1] / "roadmap_app.py")


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fake-server-key")
    response = SimpleNamespace(usage=None, choices=[SimpleNamespace(message=SimpleNamespace(
        content=f"<<ROADMAP_JSON>>\n{json.dumps(CURRICULUM)}\n<<END_ROADMAP_JSON>>",
    ))])
    client = Mock()
    client.chat.completions.create.return_value = response
    constructor = Mock(return_value=client)
    monkeypatch.setattr(weekly_planner, "OpenAI", constructor)

    def forbidden(*args, **kwargs):
        pytest.fail("Unrelated persistence, agent, memory, task, or downstream generation executed")

    for name in ("tool_generate_learning_roadmap", "_seed_roadmap_tasks", "save_tasks",
                 "tool_save_outputs", "tool_generate_weekly_plan", "tool_generate_quiz_for_day",
                 "tool_generate_learning_unit_for_day"):
        monkeypatch.setattr(tools, name, forbidden)
    monkeypatch.setattr(tools.LocalVectorStore, "__init__", forbidden)
    for name in ("run_weekly_planner_agent", "run_weekly_planner_agent_fixed",
                 "run_weekly_planner_agent_react"):
        monkeypatch.setattr(react_agent, name, forbidden)
    return constructor, client.chat.completions.create, response


def test_success_uses_shared_prompt_one_request_and_no_persistence(api, tmp_path, monkeypatch):
    constructor, create, _ = api
    monkeypatch.chdir(tmp_path)
    existing = tmp_path / "existing.txt"
    existing.write_text("Keep existing work")
    markdown = service.generate_roadmap(**INPUTS)
    assert "# Global Learning Roadmap: IAM policies" in markdown
    assert "Explain deny precedence" in markdown
    assert "hours_per_week: 3.5" in markdown
    assert "max_session_minutes: 30" in markdown
    setup = dict(INPUTS, preferences="", max_session_minutes=30)
    prompt = tools.build_roadmap_prompt(setup["goal"], "medium", setup["background"], setup)
    constructor.assert_called_once_with(api_key="fake-server-key", max_retries=0)
    create.assert_called_once()
    assert create.call_args.kwargs["model"] == service.ROADMAP_MODEL
    assert create.call_args.kwargs["messages"] == [
        {"role": "system", "content": prompt["system"]},
        {"role": "user", "content": prompt["user"]},
    ]
    assert list(tmp_path.iterdir()) == [existing]
    assert existing.read_text() == "Keep existing work"


@pytest.mark.parametrize("updates", [
    {"goal": "  "}, {"hours_per_week": 0}, {"hours_per_week": float("nan")},
    {"hours_per_week": 0.75}, {"learning_purpose": "unsupported"},
    {"learning_intensity": "unsupported"}, {"background": None},
])
def test_invalid_input_never_calls_llm(api, updates):
    constructor, create, _ = api
    with pytest.raises(ValueError):
        service.generate_roadmap(**dict(INPUTS, **updates))
    constructor.assert_not_called()
    create.assert_not_called()


@pytest.mark.parametrize("raw", [
    "secret raw response", "{}", "[]", json.dumps(dict(CURRICULUM, phases=[])),
    json.dumps(dict(CURRICULUM, target_level=[])),
])
def test_malformed_output_is_safe_without_retry(api, raw):
    _, create, response = api
    response.choices[0].message.content = raw
    with pytest.raises(service.RoadmapGenerationError, match="model returned an invalid roadmap") as exc:
        service.generate_roadmap(**INPUTS)
    assert "secret raw response" not in str(exc.value)
    create.assert_called_once()


def test_api_failure_is_safe_without_retry(api):
    constructor, create, _ = api
    create.side_effect = RuntimeError("secret API diagnostic")
    with pytest.raises(service.RoadmapGenerationError, match="server API configuration") as exc:
        service.generate_roadmap(**INPUTS)
    assert "secret API diagnostic" not in str(exc.value)
    constructor.assert_called_once_with(api_key="fake-server-key", max_retries=0)
    create.assert_called_once()


def test_form_submission_retains_result_without_regenerating_on_rerun(api):
    _, create, _ = api
    app = AppTest.from_file(APP).run()
    assert not app.exception
    create.assert_not_called()
    app.text_area[0].input("Learn IAM policies")
    app.selectbox[0].select("topic_mastery")
    app.button[0].click().run()
    assert not app.exception and not app.error
    assert "IAM policies" in app.markdown[0].value
    assert app.session_state["roadmap_markdown"].strip() == app.markdown[0].value
    create.assert_called_once()
    app.run()
    assert not app.exception and "IAM policies" in app.markdown[0].value
    create.assert_called_once()

    # A failed new submission clears the previous result and spends no request.
    app.text_area[0].input(" ")
    app.button[0].click().run()
    assert not app.exception and "check your learner inputs" in app.error[0].value
    assert not app.markdown
    create.assert_called_once()


@pytest.mark.parametrize("failure", ["api", "output"])
def test_form_displays_safe_generation_errors(api, failure):
    _, create, response = api
    if failure == "api":
        create.side_effect = RuntimeError("secret API diagnostic")
    else:
        response.choices[0].message.content = "secret raw response"
    app = AppTest.from_file(APP).run()
    app.text_area[0].input("Learn IAM policies")
    app.button[0].click().run()
    assert not app.exception and len(app.error) == 1
    assert "secret" not in app.error[0].value
    assert not app.markdown
    create.assert_called_once()
