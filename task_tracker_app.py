"""A minimal task tracker built with Streamlit."""
from pathlib import Path

import pandas as pd
import streamlit as st


TASKS_FILE = Path(__file__).parent / "tasks.csv"
REQUIRED_COLUMNS = ["id", "title", "status", "epic"]
EPIC_WEEK_ORDER = [
    ("Foundations", "Week 1"),
    ("Setup", "Week 1"),
    ("Agent_MVP", "Week 1"),
    ("Agent_v2", "Week 1"),
    ("Visibility", "Week 1"),
    ("Applied_Feature", "Week 2"),
    ("AI_App", "Week 3"),
    ("Monetization", "Week 4"),
]


def save_tasks(df: pd.DataFrame) -> None:
    """Persist tasks to CSV."""
    df.to_csv(TASKS_FILE, index=False)


def load_tasks() -> pd.DataFrame:
    """Load tasks from CSV, creating a starter file if missing or malformed."""
    if not TASKS_FILE.exists():
        df = pd.DataFrame(columns=REQUIRED_COLUMNS)
    else:
        try:
            df = pd.read_csv(TASKS_FILE)
        except pd.errors.EmptyDataError:
            df = pd.DataFrame(columns=REQUIRED_COLUMNS)

    for column in REQUIRED_COLUMNS:
        if column not in df.columns:
            # Default epic to General when absent; keep status defaulting to TODO.
            default_value = "TODO" if column == "status" else "General" if column == "epic" else ""
            df[column] = default_value

    df = df[REQUIRED_COLUMNS]
    df["title"] = df["title"].fillna("").astype(str)
    df["status"] = df["status"].fillna("TODO").astype(str)
    df["epic"] = df["epic"].fillna("General").astype(str)
    df["id"] = pd.to_numeric(df["id"], errors="coerce")

    if df["id"].isna().any():
        max_id = int(df["id"].dropna().max() or 0)
        missing_count = df["id"].isna().sum()
        df.loc[df["id"].isna(), "id"] = range(max_id + 1, max_id + 1 + missing_count)

    if not df.empty:
        df["id"] = df["id"].astype(int)

    # Ensure predefined tasks exist with their epics (case-insensitive match on title).
    predefined_tasks = [
        {"title": "Learn AI mental model", "epic": "Foundations"},
        {"title": "Learn embeddings", "epic": "Foundations"},
        {"title": "Learn agent workflow", "epic": "Foundations"},
        {"title": "Create GitHub repo", "epic": "Setup"},
        {"title": "Add folder structure", "epic": "Setup"},
        {"title": "Write README v0.1", "epic": "Setup"},
        {"title": "Set up development environment", "epic": "Setup"},
        {"title": "Define agent prompt structure", "epic": "Agent_MVP"},
        {"title": "Implement agent LLM call", "epic": "Agent_MVP"},
        {"title": "Add file-saving logic", "epic": "Agent_MVP"},
        {"title": "Run generator once", "epic": "Agent_MVP"},
        {"title": "Improve markdown formatting", "epic": "Agent_v2"},
        {"title": "Add memory feature", "epic": "Agent_v2"},
        {"title": "Commit + push MVP", "epic": "Agent_v2"},
        {"title": "Draft LinkedIn post #1", "epic": "Visibility"},
        {"title": "Add micro-feature to agent", "epic": "Visibility"},
        {"title": "Write week summary", "epic": "Visibility"},
        {"title": "Choose Week 2 feature", "epic": "Applied_Feature"},
        {"title": "Write functional spec", "epic": "Applied_Feature"},
        {"title": "Implement minimal feature", "epic": "Applied_Feature"},
        {"title": "Generate example output", "epic": "Applied_Feature"},
        {"title": "Create Streamlit skeleton", "epic": "AI_App"},
        {"title": "Integrate agent backend", "epic": "AI_App"},
        {"title": "Add vector search + memory", "epic": "AI_App"},
        {"title": "Add UI components", "epic": "AI_App"},
        {"title": "Local deployment", "epic": "AI_App"},
        {"title": "Create landing page", "epic": "Monetization"},
        {"title": "Deploy app online", "epic": "Monetization"},
        {"title": "Finalize portfolio", "epic": "Monetization"},
        {"title": "Write LinkedIn posts", "epic": "Monetization"},
        {"title": "Define SaaS MVP roadmap", "epic": "Monetization"},
    ]
    existing_titles = set(df["title"].str.strip().str.lower())
    current_max_id = int(df["id"].max()) if not df.empty else 0
    new_rows = []

    # Update epics for predefined tasks already present.
    for item in predefined_tasks:
        normalized_title = item["title"].strip().lower()
        mask = df["title"].str.strip().str.lower() == normalized_title
        if mask.any():
            df.loc[mask, "epic"] = item["epic"]

    # Add any missing predefined tasks with their epics.
    for item in predefined_tasks:
        normalized_title = item["title"].strip().lower()
        if normalized_title in existing_titles:
            continue
        current_max_id += 1
        new_rows.append(
            {"id": current_max_id, "title": item["title"], "status": "TODO", "epic": item["epic"]}
        )
        existing_titles.add(normalized_title)

    if new_rows:
        df = pd.concat([df, pd.DataFrame(new_rows, columns=REQUIRED_COLUMNS)], ignore_index=True)

    save_tasks(df)
    return df


def main() -> None:
    st.title("Task Tracker")
    st.subheader("Your tasks")

    tasks_df = load_tasks()

    filter_choice = st.radio(
        "Show",
        options=["TODO only", "All", "DONE only"],
        index=0,
        horizontal=True,
    )

    filtered_df = tasks_df
    if filter_choice == "TODO only":
        filtered_df = tasks_df[tasks_df["status"] == "TODO"]
    elif filter_choice == "DONE only":
        filtered_df = tasks_df[tasks_df["status"] == "DONE"]

    # Group tasks by epic and render checkboxes under each epic heading.
    updated = False
    epics_in_data = list(filtered_df["epic"].dropna().unique())
    week_by_epic = {name: week for name, week in EPIC_WEEK_ORDER}
    ordered_epics = []
    for epic_name, _week in EPIC_WEEK_ORDER:
        if epic_name in epics_in_data:
            ordered_epics.append(epic_name)
    extras = sorted([e for e in epics_in_data if e not in week_by_epic])
    ordered_epics.extend(extras)

    for epic in ordered_epics:
        epic_tasks = filtered_df[filtered_df["epic"] == epic]
        if epic_tasks.empty:
            continue
        has_todo = (epic_tasks["status"] != "DONE").any()
        week_label = week_by_epic.get(epic)
        expander_title = f"{week_label} — {epic}" if week_label else epic
        with st.expander(expander_title, expanded=has_todo):
            for task in epic_tasks.itertuples():
                is_done = task.status == "DONE"
                col1, col2 = st.columns([0.1, 0.9])
                with col1:
                    checked = st.checkbox(
                        "",
                        value=is_done,
                        key=f"task_{task.id}",
                    )
                with col2:
                    status_label = "🟢 DONE" if checked else "🔴 TODO"
                    st.markdown(f"**{task.title}**  {status_label}")
                if checked != is_done:
                    tasks_df.loc[tasks_df["id"] == task.id, "status"] = (
                        "DONE" if checked else "TODO"
                    )
                    updated = True

    if updated:
        save_tasks(tasks_df)
        st.experimental_rerun()

    st.subheader("Add a new task")
    new_title = st.text_input("New task title", key="new_task_title")
    if st.button("Add task"):
        title = new_title.strip()
        if not title:
            st.warning("Please enter a task title.")
        else:
            next_id = int(tasks_df["id"].max()) + 1 if not tasks_df.empty else 1
            new_row = pd.DataFrame(
                [{"id": next_id, "title": title, "status": "TODO", "epic": "General"}],
                columns=REQUIRED_COLUMNS,
            )
            tasks_df = pd.concat([tasks_df, new_row], ignore_index=True)
            save_tasks(tasks_df)
            st.success("Task added.")
            st.session_state["new_task_title"] = ""
            st.experimental_rerun()


if __name__ == "__main__":
    main()
