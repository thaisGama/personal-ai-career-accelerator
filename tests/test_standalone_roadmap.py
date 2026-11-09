"""Standalone generation and Streamlit reruns; no paid API calls."""

import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.agent import react_agent, tools, weekly_planner
from standalone_roadmap import service
from standalone_roadmap.admission import AdmissionController


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
    monkeypatch.setenv("ROADMAP_ENVIRONMENT", "beta")
    monkeypatch.delenv("ROADMAP_DAILY_LIMIT", raising=False)
    monkeypatch.delenv("ROADMAP_GENERATION_ENABLED", raising=False)
    monkeypatch.setattr(service, "admission_controller", AdmissionController())
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
    constructor.assert_called_once_with(
        api_key="fake-server-key", max_retries=0, timeout=service.ROADMAP_TIMEOUT_SECONDS,
    )
    create.assert_called_once()
    assert create.call_args.kwargs["max_completion_tokens"] == service.ROADMAP_MAX_TOKENS
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
def test_invalid_input_never_calls_llm(api, updates, monkeypatch):
    monkeypatch.setenv("ROADMAP_DAILY_LIMIT", "1")
    constructor, create, _ = api
    with pytest.raises(ValueError):
        service.generate_roadmap(**dict(INPUTS, **updates))
    constructor.assert_not_called()
    create.assert_not_called()
    assert service.generate_roadmap(**INPUTS)
    create.assert_called_once()


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
    constructor.assert_called_once_with(
        api_key="fake-server-key", max_retries=0, timeout=service.ROADMAP_TIMEOUT_SECONDS,
    )
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


def test_download_uses_current_session_markdown_without_regeneration(api, monkeypatch):
    _, create, response = api
    download = Mock(wraps=st.download_button)
    monkeypatch.setattr(st, "download_button", download)
    app = AppTest.from_file(APP).run()
    download.assert_not_called()

    app.text_area[0].input("Learn IAM policies")
    app.button[0].click().run()
    assert not app.exception
    download.assert_called_once_with(
        "Download roadmap as Markdown", data=app.session_state["roadmap_markdown"],
        file_name="learning-roadmap.md", mime="text/markdown", on_click="ignore",
    )
    assert app.get("download_button")[0].proto.ignore_rerun
    create.assert_called_once()

    # Editing the form and rerunning must still download the displayed result.
    download.reset_mock()
    app.text_area[0].input("An unsubmitted different goal").run()
    assert not app.exception
    assert download.call_args.kwargs["data"] == app.session_state["roadmap_markdown"]
    create.assert_called_once()

    # A new successful generation replaces both the display and the download.
    response.choices[0].message.content = json.dumps(dict(CURRICULUM, topic="New topic — café"))
    download.reset_mock()
    app.button[0].click().run()
    assert not app.exception
    assert "New topic — café" in app.markdown[0].value
    assert download.call_args.kwargs["data"] == app.session_state["roadmap_markdown"]
    assert "New topic — café" in download.call_args.kwargs["data"]
    assert create.call_count == 2

    # A failed submission removes both the old roadmap and its download.
    download.reset_mock()
    app.text_area[0].input(" ")
    app.button[0].click().run()
    assert not app.exception and app.error
    download.assert_not_called()
    assert not app.get("download_button")
    assert create.call_count == 2


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


@pytest.mark.parametrize("field,limit", [
    ("goal", service.MAX_GOAL_CHARACTERS),
    ("background", service.MAX_BACKGROUND_CHARACTERS),
])
def test_input_length_boundary_is_accepted(api, field, limit):
    _, create, _ = api
    assert service.generate_roadmap(**dict(INPUTS, **{field: "é" * limit}))
    create.assert_called_once()


@pytest.mark.parametrize("field,label,limit", [
    ("goal", "Learning goal", service.MAX_GOAL_CHARACTERS),
    ("background", "Background", service.MAX_BACKGROUND_CHARACTERS),
])
@pytest.mark.parametrize("padding", ["x", " "])
def test_oversized_input_rejected_before_llm(api, field, label, limit, padding):
    constructor, create, _ = api
    with pytest.raises(ValueError, match=f"{label} must be {limit:,} characters or fewer"):
        service.generate_roadmap(**dict(INPUTS, **{field: "x" * limit + padding}))
    constructor.assert_not_called()
    create.assert_not_called()


def test_custom_timeout_reaches_api_client(api):
    constructor, create, _ = api
    service.generate_roadmap(**INPUTS, timeout_seconds=45.5)
    constructor.assert_called_once_with(api_key="fake-server-key", max_retries=0, timeout=45.5)
    create.assert_called_once()
    assert create.call_args.kwargs["max_completion_tokens"] == service.ROADMAP_MAX_TOKENS


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), None, True])
def test_invalid_timeout_rejected_before_llm(api, timeout):
    constructor, create, _ = api
    with pytest.raises(ValueError, match="positive, finite"):
        service.generate_roadmap(**INPUTS, timeout_seconds=timeout)
    constructor.assert_not_called()
    create.assert_not_called()


def test_timeout_failure_has_no_retry(api):
    import openai

    constructor, create, _ = api
    create.side_effect = openai.APITimeoutError(request=Mock())
    with pytest.raises(service.RoadmapGenerationError, match="connection"):
        service.generate_roadmap(**INPUTS)
    constructor.assert_called_once_with(
        api_key="fake-server-key", max_retries=0, timeout=service.ROADMAP_TIMEOUT_SECONDS,
    )
    create.assert_called_once()


def test_beta_default_allows_ten_attempts(api):
    _, create, _ = api
    for _ in range(10):
        service.generate_roadmap(**INPUTS)
    with pytest.raises(service.RoadmapUnavailableError, match="midnight UTC"):
        service.generate_roadmap(**INPUTS)
    assert create.call_count == 10


def test_development_has_no_daily_quota_by_default(api, monkeypatch):
    monkeypatch.setenv("ROADMAP_ENVIRONMENT", "development")
    _, create, _ = api
    for _ in range(11):
        service.generate_roadmap(**INPUTS)
    assert create.call_count == 11


@pytest.mark.parametrize("failure", [None, "api", "output"])
def test_capacity_released_and_admitted_failures_count(api, monkeypatch, failure):
    monkeypatch.setenv("ROADMAP_DAILY_LIMIT", "2")
    _, create, response = api
    if failure == "api":
        create.side_effect = RuntimeError("private diagnostic")
    elif failure == "output":
        response.choices[0].message.content = "invalid"
    if failure:
        with pytest.raises(service.RoadmapGenerationError):
            service.generate_roadmap(**INPUTS)
    else:
        service.generate_roadmap(**INPUTS)
    create.side_effect = None
    response.choices[0].message.content = json.dumps(CURRICULUM)
    assert service.generate_roadmap(**INPUTS)
    with pytest.raises(service.RoadmapUnavailableError, match="allowance"):
        service.generate_roadmap(**INPUTS)
    assert create.call_count == 2


@pytest.mark.parametrize("settings", [
    {"ROADMAP_GENERATION_ENABLED": "false"},
    {"ROADMAP_ENVIRONMENT": "typo-private-value"},
    {"ROADMAP_DAILY_LIMIT": "unlimited"},
    {"ROADMAP_GENERATION_ENABLED": "yes"},
    {"OPENAI_API_KEY": ""},
])
def test_disabled_or_misconfigured_requests_spend_no_quota(api, monkeypatch, settings):
    monkeypatch.setenv("ROADMAP_DAILY_LIMIT", "1")
    constructor, create, _ = api
    with monkeypatch.context() as change:
        for key, value in settings.items():
            change.setenv(key, value)
        with pytest.raises(service.RoadmapUnavailableError) as exc:
            service.generate_roadmap(**INPUTS)
        assert "private-value" not in str(exc.value)
    constructor.assert_not_called()
    create.assert_not_called()
    assert service.generate_roadmap(**INPUTS)
    create.assert_called_once()


def test_concurrent_generation_rejected_without_spending_quota(api, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    monkeypatch.setenv("ROADMAP_DAILY_LIMIT", "2")
    _, create, response = api
    entered, release = Event(), Event()

    def blocked_api(**kwargs):
        entered.set()
        assert release.wait(5), "Test did not release the API request"
        return response

    create.side_effect = blocked_api
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(service.generate_roadmap, **INPUTS)
        try:
            assert entered.wait(5), "Generation did not reach the mocked API"
            with pytest.raises(service.RoadmapUnavailableError, match="being generated"):
                service.generate_roadmap(**INPUTS)
            create.assert_called_once()
        finally:
            release.set()
        assert pending.result(timeout=5)
    create.side_effect = None
    assert service.generate_roadmap(**INPUTS)
    assert create.call_count == 2


def test_allowance_shared_across_streamlit_sessions(api, monkeypatch):
    monkeypatch.setenv("ROADMAP_DAILY_LIMIT", "1")
    _, create, _ = api
    first, second = AppTest.from_file(APP).run(), AppTest.from_file(APP).run()
    first.text_area[0].input("First learner's goal")
    first.button[0].click().run()
    assert not first.exception and first.markdown
    second.text_area[0].input("Second learner's goal")
    second.button[0].click().run()
    assert not second.exception and "allowance" in second.error[0].value
    assert not second.markdown
    create.assert_called_once()


def test_invalid_form_edits_downloads_and_reruns_spend_no_quota(api, monkeypatch):
    monkeypatch.setenv("ROADMAP_DAILY_LIMIT", "1")
    _, create, _ = api
    app = AppTest.from_file(APP).run()
    app.text_area[0].input(" ")
    app.button[0].click().run()
    assert not app.exception and app.error
    create.assert_not_called()
    app.text_area[0].input("Learn IAM policies")
    app.button[0].click().run()
    assert not app.exception and not app.error
    markdown = app.session_state["roadmap_markdown"]
    app.text_area[0].input("Unsubmitted edit").run()
    app.run()
    assert not app.exception
    assert app.get("download_button")[0].proto.ignore_rerun
    assert app.get("download_button")[0].proto.url
    create.assert_called_once()
    # The next submitted attempt must still see the original quota usage.
    app.button[0].click().run()
    assert not app.exception and "allowance" in app.error[0].value
    assert app.session_state["roadmap_markdown"] == markdown
    create.assert_called_once()


def test_kill_switch_preserves_previous_result_and_download(api, monkeypatch):
    _, create, _ = api
    app = AppTest.from_file(APP).run()
    app.text_area[0].input("Learn IAM policies")
    app.button[0].click().run()
    markdown = app.session_state["roadmap_markdown"]
    monkeypatch.setenv("ROADMAP_GENERATION_ENABLED", "false")
    app.run()
    assert app.session_state["roadmap_markdown"] == markdown
    app.button[0].click().run()
    assert not app.exception and "temporarily disabled" in app.error[0].value
    assert app.session_state["roadmap_markdown"] == markdown
    assert app.markdown[0].value == markdown.strip()
    assert app.get("download_button")
    create.assert_called_once()
