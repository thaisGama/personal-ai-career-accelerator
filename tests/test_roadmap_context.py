"""Roadmap isolation and honest progress, using saved IDs rather than topics."""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agent.learning_progress_store import (
    append_week_from_plan, update_day_learning_unit_path, update_day_validation_result,
)
from src.core.services.roadmap_context import (
    day_status, learning_units, progress_summary, read_progress, roadmap_weeks,
    saved_resource, switch_roadmap,
)


PLAN = "# Week 1 Learning Plan\n\n🧩 Learning Days (10–30 min)\n- **Day 1 (20 min): Shared topic**\n"


def test_new_weeks_keep_exact_roadmap_and_artifact_associations(tmp_path):
    path = tmp_path / "data" / "learning_progress.json"
    append_week_from_plan(path, PLAN, roadmap_id="alpha", plan_path="weekly_plans/a.md",
                          learning_unit_path="docs/learning_units/a.md")
    append_week_from_plan(path, PLAN, roadmap_id="beta", plan_path="weekly_plans/b.md",
                          learning_unit_path="docs/learning_units/b.md")
    weeks, error = read_progress(tmp_path)
    assert error is None
    assert roadmap_weeks(weeks, "alpha")[0]["plan_path"] == "weekly_plans/a.md"
    assert roadmap_weeks(weeks, "beta")[0]["learning_unit_path"] == "docs/learning_units/b.md"
    assert len(roadmap_weeks(weeks, "alpha")) == 1


def test_linked_quiz_updates_correct_day_without_crossing_roadmaps(tmp_path):
    path = tmp_path / "data" / "learning_progress.json"
    append_week_from_plan(path, PLAN, roadmap_id="alpha")
    append_week_from_plan(path, PLAN, roadmap_id="beta")
    update_day_learning_unit_path(path, "day_001", "docs/learning_units/a.md")
    weeks, _ = read_progress(tmp_path)
    assert progress_summary(roadmap_weeks(weeks, "alpha"))["completed"] == 0
    update_day_validation_result(path, "day_001", "PASS")
    update_day_validation_result(path, "day_002", "FAIL")
    weeks, _ = read_progress(tmp_path)
    assert progress_summary(roadmap_weeks(weeks, "alpha"))["completed"] == 1
    beta = roadmap_weeks(weeks, "beta")
    assert progress_summary(beta)["completed"] == 0
    assert day_status(beta[0]["days"][0]) == "Needs review"


def test_legacy_top_level_owner_is_not_used_for_mixed_weeks(tmp_path):
    path = tmp_path / "data" / "learning_progress.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"roadmap_id": "alpha", "weeks": [
        {"goal": "Alpha", "days": [{"status": "PASSED"}]},
        {"goal": "Beta", "days": [{"quiz_result": "PASS"}]},
    ]}))
    before = path.read_bytes()
    weeks, error = read_progress(tmp_path)
    assert error is None and roadmap_weeks(weeks, "alpha") == []
    assert path.read_bytes() == before


def test_completion_requires_pass_and_reviews_do_not_inflate_core_progress():
    passed = {"quiz_result": "PASS", "day_id": "one"}
    unknown = {"status": "PASSED", "learning_unit_path": "generated.md"}
    failed = {"quiz_result": "FAIL", "day_id": "two"}
    review = {"quiz_result": "", "is_review": True, "review_of_day_id": "two"}
    week = {"days": [passed, unknown, failed, review]}
    summary = progress_summary([week])
    assert summary["total"] == 3 and summary["completed"] == 1
    assert summary["unknown"] == 1 and summary["review_total"] == 1
    assert summary["recommended"] == (week, review)
    assert day_status(unknown) == "Progress unavailable"
    assert day_status({"status": "DONE", "quiz_result": ""}) == "Not started"


def test_library_uses_exact_paths_and_omits_conflicting_or_unknown_links(tmp_path):
    library = tmp_path / "docs" / "learning_units"
    library.mkdir(parents=True)
    for name in ("a.md", "b.md", "unknown.md", "conflict.md"):
        (library / name).write_text("# Same topic\nContent unchanged")
    weeks = [
        {"roadmap_id": "alpha", "week_number_global": 2,
         "learning_unit_path": "docs/learning_units/a.md", "days": [
             {"day_number": 3, "learning_unit_path": "docs/learning_units/conflict.md"}]},
        {"roadmap_id": "beta", "days": [
            {"day_number": 1, "learning_unit_path": "docs/learning_units/b.md"},
            {"day_number": 2, "learning_unit_path": "docs/learning_units/conflict.md"}]},
    ]
    entries = learning_units(tmp_path, weeks, "alpha")
    assert list(entries) == [(library / "a.md").resolve()]
    assert entries[(library / "a.md").resolve()]["day"] is None
    all_entries = learning_units(tmp_path, weeks, None)
    assert all_entries[(library / "unknown.md").resolve()] == {}
    assert all_entries[(library / "conflict.md").resolve()] == {}
    assert saved_resource(tmp_path, "../../outside.md", "docs/learning_units") is None


def test_switch_clears_stale_context_but_preserves_inputs_and_same_roadmap():
    state = {"workspace_roadmap_id": "alpha", "planner_result": {"roadmap_id": "alpha"},
             "planner_plan_md": "Alpha preview", "learning_unit_select": "a.md",
             "quiz_markdown": "Alpha quiz", "quiz_answer_1": "Answer", "planner_goal": "Draft"}
    switch_roadmap(state, "alpha")
    assert state["planner_plan_md"] == "Alpha preview"
    switch_roadmap(state, "beta")
    assert state["active_roadmap_id"] == state["quiz_roadmap_id"] == "beta"
    assert state["planner_goal"] == "Draft"
    assert not any(k in state for k in ("planner_result", "planner_plan_md", "learning_unit_select", "quiz_markdown", "quiz_answer_1"))


def test_unreadable_progress_has_explicit_fallback_without_writes(tmp_path):
    assert read_progress(tmp_path) == ([], None)
    assert not (tmp_path / "data").exists()
    path = tmp_path / "data" / "learning_progress.json"
    path.parent.mkdir()
    path.write_text("broken")
    weeks, error = read_progress(tmp_path)
    assert weeks == [] and "Progress unavailable" in error
    assert path.read_text() == "broken"
