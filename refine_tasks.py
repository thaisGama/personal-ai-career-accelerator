"""
Utility script to append refined sub-tasks to tasks.csv without changing the app UI.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

TASKS_FILE = Path(__file__).parent / "tasks.csv"
REQUIRED_COLUMNS = ["id", "title", "status", "epic", "description"]
STATUS_OPTIONS = ["TODO", "IN_PROGRESS", "DONE"]

NEW_TASKS = [
    # Visibility
    {
        "title": "Add priority tags to tasks (🔥 ★ 🌱)",
        "epic": "Visibility",
        "description": "Update planner output format to include a priority symbol for each task so you can quickly see what matters most.",
    },
    {
        "title": "Add resource suggestions to learning tasks",
        "epic": "Visibility",
        "description": "Extend the planner output so each learning task has 1–2 concrete resource suggestions (link or name).",
    },
    {
        "title": "Add 'learning capsule' snippet",
        "epic": "Visibility",
        "description": "At the end of the weekly plan, generate a bullet list of key concepts you will know after completing the week.",
    },
    {
        "title": "Add 'output deliverables' section",
        "epic": "Visibility",
        "description": "Add a section listing the concrete artifacts you will produce (files, posts, app features) for the week.",
    },
    # Agent_v2 — Memory Feature Phase 1
    {
        "title": "Design memory file format for /docs/memory.md",
        "epic": "Agent_v2",
        "description": "Decide on the structure of /docs/memory.md (date, week, bullets) so weekly summaries are consistent.",
    },
    {
        "title": "Implement append_memory_snippet() function",
        "epic": "Agent_v2",
        "description": "Write a Python function that appends a new 'Week X' block to /docs/memory.md, creating the file if needed.",
    },
    {
        "title": "Wire planner to call append_memory_snippet()",
        "epic": "Agent_v2",
        "description": "Call append_memory_snippet() at the end of the weekly planning flow to store a short summary of the week.",
    },
    {
        "title": "Test memory append end-to-end",
        "epic": "Agent_v2",
        "description": "Run the planner once, inspect /docs/memory.md, and verify the new entry has the right format and content.",
    },
    {
        "title": "Document memory behavior",
        "epic": "Agent_v2",
        "description": "Add a short explanation (README or /docs/memory_system.md) of what the memory file contains and how it is used.",
    },
    # Applied_Feature — Memory Feature Phase 2
    {
        "title": "Load memory.md content in planner",
        "epic": "Applied_Feature",
        "description": "Read /docs/memory.md in the planner, handling the case where the file does not exist or is empty.",
    },
    {
        "title": "Extract last week's key learnings",
        "epic": "Applied_Feature",
        "description": "Implement a simple heuristic to grab the most recent section from memory.md and extract its main bullet points.",
    },
    {
        "title": "Inject memory context into planner prompt",
        "epic": "Applied_Feature",
        "description": "Include a 'Recent learnings' block in the LLM prompt that uses the extracted memory context.",
    },
    {
        "title": "Adjust tasks based on memory",
        "epic": "Applied_Feature",
        "description": "Modify the planner logic so it can reuse incomplete tasks or avoid repeating topics that were already covered.",
    },
    {
        "title": "Test planner behavior with and without memory",
        "epic": "Applied_Feature",
        "description": "Generate two weekly plans (with and without memory) and compare to ensure the memory context actually changes the plan.",
    },
]


def ensure_columns(df: pd.DataFrame, original_columns: list[str]) -> pd.DataFrame:
    """Ensure required columns exist and basic defaults are applied."""
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            default_value = (
                "TODO"
                if col == "status"
                else "General"
                if col == "epic"
                else ""
            )
            df[col] = default_value

    df["title"] = df["title"].fillna("").astype(str)
    df["description"] = df["description"].fillna("").astype(str)
    df["epic"] = df["epic"].fillna("General").astype(str)
    df["status"] = df["status"].fillna("TODO").astype(str)
    df.loc[~df["status"].isin(STATUS_OPTIONS), "status"] = "TODO"
    df["id"] = pd.to_numeric(df["id"], errors="coerce")

    if df["id"].isna().any():
        max_id = int(df["id"].dropna().max() or 0)
        missing = df["id"].isna().sum()
        df.loc[df["id"].isna(), "id"] = range(max_id + 1, max_id + 1 + missing)

    df["id"] = df["id"].astype(int) if not df.empty else df["id"]

    # Preserve original column order and append any new required columns at the end.
    final_columns = list(original_columns)
    for col in df.columns:
        if col not in final_columns:
            final_columns.append(col)

    return df[final_columns]


def append_new_tasks(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Append new tasks if they do not already exist (title match)."""
    existing_titles = set(df["title"].str.strip().str.lower())
    next_id = int(df["id"].max()) + 1 if not df.empty else 1
    added = 0

    for item in NEW_TASKS:
        normalized_title = item["title"].strip().lower()
        if normalized_title in existing_titles:
            continue

        row = {col: "" for col in df.columns}
        row.update(
            {
                "id": next_id,
                "title": item["title"],
                "status": "TODO",
                "epic": item["epic"],
                "description": item.get("description", ""),
            }
        )
        df = pd.concat([df, pd.DataFrame([row], columns=df.columns)], ignore_index=True)
        existing_titles.add(normalized_title)
        next_id += 1
        added += 1

    return df, added


def main() -> None:
    if TASKS_FILE.exists():
        df = pd.read_csv(TASKS_FILE)
        original_columns = list(df.columns)
    else:
        df = pd.DataFrame(columns=REQUIRED_COLUMNS)
        original_columns = list(df.columns)

    df = ensure_columns(df, original_columns)
    df, added = append_new_tasks(df)
    df.to_csv(TASKS_FILE, index=False)
    print(f"Refinement complete. Added {added} new tasks. Total rows: {len(df)}.")


if __name__ == "__main__":
    main()
