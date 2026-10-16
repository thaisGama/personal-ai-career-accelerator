"""Prompt identity and deterministic rendering contracts, without API calls."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.agent import prompts, tools

FIXTURES = Path(__file__).parent / "fixtures" / "prompts"


def test_template_versions_and_hashes_are_explicitly_reviewed():
    metadata = prompts.list_prompt_metadata()
    assert metadata == json.loads((FIXTURES / "template_metadata.json").read_text(encoding="utf-8"))
    assert metadata == [prompts.get_prompt_metadata(item["prompt_id"]) for item in metadata]
    # Guard against templates silently omitted from the version registry.
    template_ids = {
        path.relative_to(prompts._ROOT / "templates").with_suffix("").as_posix().replace("/", ".")
        for path in (prompts._ROOT / "templates").rglob("*.txt")
    }
    assert template_ids == {item["prompt_id"] for item in metadata}


def test_rendering_is_independent_of_working_directory_and_does_not_reinterpret_values(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    value = "  {unknown} {{braces}} $value — café\n\n"
    before = prompts.get_prompt_metadata("quiz.user")
    assert prompts.render_prompt("quiz.user", topic=value, context_text="", tasks_block="") == (
        f"Topic: {value}\nContext/notes (may be empty):\n\nGenerate the quiz now."
    )
    assert prompts.get_prompt_metadata("quiz.user") == before


def test_missing_runtime_value_fails_instead_of_sending_an_unresolved_placeholder():
    with pytest.raises(KeyError, match="goal"):
        prompts.render_prompt("roadmap.user")


@pytest.mark.parametrize("prompt_id", ["unknown.system", "../versions", "/tmp/prompt"])
def test_unknown_ids_cannot_load_unregistered_files(prompt_id):
    with pytest.raises(KeyError, match="Unknown prompt ID"):
        prompts.render_prompt(prompt_id)
    with pytest.raises(KeyError, match="Unknown prompt ID"):
        prompts.get_prompt_metadata(prompt_id)


@pytest.mark.parametrize("memory", ["", " \n ", "  Existing memory {braces}\n"])
def test_weekly_tool_preserves_original_empty_memory_policy(tmp_path, monkeypatch, memory):
    captured = {}

    def generate(**kwargs):
        captured.update(kwargs)
        return {}

    monkeypatch.setattr(tools, "generate_weekly_plan_and_learning_unit", generate)
    tools.tool_generate_weekly_plan("RAG", 2, 20, {}, memory, {}, "test", tmp_path)
    assert captured["memory_context"] == (
        memory if memory.strip()
        else "There is no relevant past memory yet. Plan as if this is the first week.\n"
    )
