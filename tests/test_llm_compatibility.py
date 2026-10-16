"""Request compatibility at the shared LLM boundary, without network calls."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agent import weekly_planner


@pytest.fixture
def mocked_openai(monkeypatch):
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="  unchanged response\n"))],
        usage=None,
    )
    client = Mock()
    client.chat.completions.create.return_value = response
    constructor = Mock(return_value=client)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-a-real-credential")
    monkeypatch.setattr(weekly_planner, "OpenAI", constructor)
    return constructor, client.chat.completions.create


@pytest.mark.parametrize("model", ["gpt-6-luna", "gpt-4o-mini", "gpt-4.1-mini", "gpt-6-sol"])
@pytest.mark.parametrize("options", [
    {},
    {"temperature": 0.0, "max_tokens": 2200},
    {"temperature": 0.5, "max_tokens": 2800},
])
def test_model_request_preserves_prompts_temperature_budget_and_response(mocked_openai, model, options):
    constructor, create = mocked_openai

    result = weekly_planner.call_llm("System prompt", "User prompt", model=model, **options)

    budget = options.get("max_tokens", weekly_planner.MAX_TOKENS)
    expected = {
        "model": model,
        "messages": [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "User prompt"},
        ],
        "temperature": options.get("temperature", 0.5),
    }
    if model == "gpt-6-luna":
        expected.update(reasoning_effort="none", max_completion_tokens=budget)
    else:
        expected.update(max_tokens=budget)
    constructor.assert_called_once_with(api_key="test-key-not-a-real-credential")
    create.assert_called_once_with(**expected)
    assert result == "  unchanged response\n"


def test_usage_log_records_returned_model_and_token_counts(mocked_openai, capsys):
    _constructor, create = mocked_openai
    create.return_value.model = "returned-model-snapshot"
    create.return_value.usage = SimpleNamespace(prompt_tokens=100, completion_tokens=25, total_tokens=125)

    result = weekly_planner.call_llm("System prompt", "User prompt", model="gpt-6-luna")

    assert capsys.readouterr().out == (
        "[WeeklyPlanner] Token usage — model: returned-model-snapshot, prompt: 100, "
        "completion: 25, total: 125\n"
    )
    assert result == "  unchanged response\n"
