"""Smoke test for roadmap generation + reuse in the ReAct loop.

Requires OPENAI_API_KEY. Run: python scripts/run_roadmap_smoke.py
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.react_agent import run_weekly_planner_agent_react


def _count_tool_calls(trace_path: Path, tool_name: str) -> int:
    data = json.loads(trace_path.read_text(encoding="utf-8"))
    return sum(1 for entry in data if entry.get("tool_name") == f"tool_{tool_name}")


def _run_once(goal: str, roadmap_id: str, base_dir: Path) -> dict:
    return run_weekly_planner_agent_react(
        goal=goal,
        hours_per_week=2,
        max_session_minutes=30,
        preferences={
            "text": "Roadmap smoke test",
            "target_level": "medium",
            "background": "",
            "roadmap_id": roadmap_id,
        },
        model="gpt-4o-mini",
        base_dir=base_dir,
        max_steps=10,
    )


if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parents[1]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    goal = f"Roadmap smoke test {stamp}"
    roadmap_id = f"roadmap_smoke_{stamp}"

    print("Running first pass (should generate roadmap)...")
    first = _run_once(goal, roadmap_id, base_dir)
    trace1 = Path(first.get("trace_path", ""))
    if trace1.is_file():
        gen_calls = _count_tool_calls(trace1, "generate_learning_roadmap")
        print(f"generate_learning_roadmap calls: {gen_calls}")
    else:
        print("No trace file found for first run.")

    print("Running second pass (should load existing roadmap)...")
    second = _run_once(goal, roadmap_id, base_dir)
    trace2 = Path(second.get("trace_path", ""))
    if trace2.is_file():
        gen_calls = _count_tool_calls(trace2, "generate_learning_roadmap")
        print(f"generate_learning_roadmap calls: {gen_calls}")
        if gen_calls != 0:
            raise RuntimeError("Expected no roadmap generation on second run.")
    else:
        print("No trace file found for second run.")
