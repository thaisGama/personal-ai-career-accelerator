"""A minimal task tracker built with Streamlit."""
from pathlib import Path

import pandas as pd
import streamlit as st


TASKS_FILE = Path(__file__).parent / "tasks.csv"
REQUIRED_COLUMNS = ["id", "title", "status", "epic", "description"]
STATUS_OPTIONS = ["TODO", "IN_PROGRESS", "DONE"]
EPIC_META = {
    "Foundations": {
        "icon": "🎓",
        "label": "Learning Foundations",
    },
    "Setup": {
        "icon": "🛠️",
        "label": "Repo & Environment",
    },
    "Agent_MVP": {
        "icon": "🔵",
        "label": "Planner Foundation (technical)",
    },
    "Agent_v2": {
        "icon": "🟢",
        "label": "Planner v2 — micro-features & memory",
    },
    "Visibility": {
        "icon": "💛",
        "label": "Visibility / Motivation / Portfolio",
    },
    "Applied_Feature": {
        "icon": "🔥",
        "label": "Memory v2 + Mini Project Engine",
    },
    "AI_App": {
        "icon": "💥",
        "label": "AI App — Product Shell",
    },
    "Monetization": {
        "icon": "🟩",
        "label": "Monetization & Positioning",
    },
    "General": {
        "icon": "⚪",
        "label": "General / Misc",
    },
}
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


def status_display(status: str) -> str:
    if status == "DONE":
        return "🟢 DONE"
    if status == "IN_PROGRESS":
        return "🟡 IN PROGRESS"
    return "🔴 TODO"


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
            # Default epic to General when absent; keep status defaulting to TODO; description empty.
            default_value = (
                "TODO"
                if column == "status"
                else "General"
                if column == "epic"
                else ""
            )
            df[column] = default_value

    df = df[REQUIRED_COLUMNS]
    df["title"] = df["title"].fillna("").astype(str)
    df["status"] = df["status"].fillna("TODO").astype(str)
    df.loc[~df["status"].isin(STATUS_OPTIONS), "status"] = "TODO"
    df["epic"] = df["epic"].fillna("General").astype(str)
    df["description"] = df["description"].fillna("").astype(str)
    df["id"] = pd.to_numeric(df["id"], errors="coerce")

    if df["id"].isna().any():
        max_id = int(df["id"].dropna().max() or 0)
        missing_count = df["id"].isna().sum()
        df.loc[df["id"].isna(), "id"] = range(max_id + 1, max_id + 1 + missing_count)

    if not df.empty:
        df["id"] = df["id"].astype(int)

    # Ensure predefined tasks exist with their epics (case-insensitive match on title).
    predefined_tasks = [
        {
            "title": "Learn AI mental model",
            "epic": "Foundations",
            "description": "Read a short explanation of LLM + memory + tools and be able to explain it in your own words.",
        },
        {
            "title": "Learn embeddings",
            "epic": "Foundations",
            "description": "Understand what embeddings are, how they encode meaning, and how they’re used with vector search.",
        },
        {
            "title": "Learn agent workflow",
            "epic": "Foundations",
            "description": "Learn the basic agent loop: understand → choose tool → act → observe → repeat.",
        },
        {
            "title": "Create GitHub repo",
            "epic": "Setup",
            "description": "Create the personal-ai-career-accelerator repo (local + remote) for all project code.",
        },
        {
            "title": "Add folder structure",
            "epic": "Setup",
            "description": "Create base folders: /agent, /weekly_plans, /tasks, /posts, /docs.",
        },
        {
            "title": "Write README v0.1",
            "epic": "Setup",
            "description": "Draft a short README describing goal, roadmap, and current status.",
        },
        {
            "title": "Set up development environment",
            "epic": "Setup",
            "description": "Create venv/devcontainer, install dependencies, ensure `streamlit run` works.",
        },
        {
            "title": "Define agent prompt structure",
            "epic": "Agent_MVP",
            "description": "Write the prompt template that takes your goal + time and outputs a 1-week plan with micro-tasks and a mini-project.",
        },
        {
            "title": "Implement agent LLM call",
            "epic": "Agent_MVP",
            "description": "Create a Python function that calls the OpenAI API with that prompt and returns markdown.",
        },
        {
            "title": "Add file-saving logic",
            "epic": "Agent_MVP",
            "description": "Save generated plans to /weekly_plans/week_XX_plan.md and LinkedIn drafts to /posts/.",
        },
        {
            "title": "Run generator once",
            "epic": "Agent_MVP",
            "description": "Run the planner once end-to-end and review the output.",
        },
        {
            "title": "Improve markdown formatting",
            "epic": "Agent_v2",
            "description": "Make the generated plan easy to read: headings, bullet lists, durations, priorities.",
        },
        {
            "title": "Add memory feature",
            "epic": "Agent_v2",
            "description": "After each week, append a short summary of completed work to /docs/memory.md and feed it into future plans.",
        },
        {
            "title": "Commit + push MVP",
            "epic": "Agent_v2",
            "description": "Stage, commit, and push all current changes (agent + planner + tracker) to GitHub with a clear message.",
        },
        {
            "title": "Draft LinkedIn post #1",
            "epic": "Visibility",
            "description": "Write a short post announcing you’re building your personal AI career accelerator (what, why, how).",
        },
        {
            "title": "Add micro-feature to agent",
            "epic": "Visibility",
            "description": "Add one small improvement to planner output, e.g. duration labels or priority tags for each task.",
        },
        {
            "title": "Write week summary",
            "epic": "Visibility",
            "description": "Write 3–5 sentences in /docs/week1_summary.md about what you learned and built this week.",
        },
        {
            "title": "Choose Week 2 feature",
            "epic": "Applied_Feature",
            "description": "Decide which product-core feature to build (course summarizer, journaling insights, LinkedIn generator, etc.).",
        },
        {
            "title": "Write functional spec",
            "epic": "Applied_Feature",
            "description": "Write a 0.5–1 page spec describing inputs, outputs, and main steps for that feature.",
        },
        {
            "title": "Implement minimal feature",
            "epic": "Applied_Feature",
            "description": "Code the smallest working version of that feature without polishing.",
        },
        {
            "title": "Generate example output",
            "epic": "Applied_Feature",
            "description": "Run the feature on a real input and save the result under /docs/examples/.",
        },
        {
            "title": "Create Streamlit skeleton",
            "epic": "AI_App",
            "description": "Create a basic multi-section Streamlit app (navigation, layout) for your AI assistant.",
        },
        {
            "title": "Integrate agent backend",
            "epic": "AI_App",
            "description": "Wire the weekly planner and one feature into the app so they can be triggered from the UI.",
        },
        {
            "title": "Add vector search + memory",
            "epic": "AI_App",
            "description": "Add a simple vector store for notes/summaries and let the app query them.",
        },
        {
            "title": "Add UI components",
            "epic": "AI_App",
            "description": "Add inputs, buttons, and result sections to make the app pleasant to use.",
        },
        {
            "title": "Local deployment",
            "epic": "AI_App",
            "description": "Be able to start the app locally and use all core features without errors.",
        },
        {
            "title": "Create landing page",
            "epic": "Monetization",
            "description": "Write a simple landing page or README section explaining who the app is for and what problem it solves.",
        },
        {
            "title": "Deploy app online",
            "epic": "Monetization",
            "description": "Deploy the Streamlit app (Streamlit Cloud / Hugging Face / etc.) so it’s available via URL.",
        },
        {
            "title": "Finalize portfolio",
            "epic": "Monetization",
            "description": "Update your portfolio/profile with repo link, app link, and key screenshots.",
        },
        {
            "title": "Write LinkedIn posts",
            "epic": "Monetization",
            "description": "Write 2 posts: one about the app, one about your learning journey and what you offer.",
        },
        {
            "title": "Define SaaS MVP roadmap",
            "epic": "Monetization",
            "description": "Outline the next 5–10 features, pricing idea, and steps to turn this into a paid product.",
        },
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
            df.loc[mask, "description"] = item.get("description", "")

    # Add any missing predefined tasks with their epics.
    for item in predefined_tasks:
        normalized_title = item["title"].strip().lower()
        if normalized_title in existing_titles:
            continue
        current_max_id += 1
        new_rows.append(
            {
                "id": current_max_id,
                "title": item["title"],
                "status": "TODO",
                "epic": item["epic"],
                "description": item.get("description", ""),
            }
        )
        existing_titles.add(normalized_title)

    if new_rows:
        df = pd.concat([df, pd.DataFrame(new_rows, columns=REQUIRED_COLUMNS)], ignore_index=True)

    save_tasks(df)
    return df


def main() -> None:
    tasks_df = load_tasks()
    total_tasks = len(tasks_df)
    num_todo = int((tasks_df["status"] == "TODO").sum())
    num_in_progress = int((tasks_df["status"] == "IN_PROGRESS").sum())
    num_done = int((tasks_df["status"] == "DONE").sum())
    percent_done = round(100 * num_done / total_tasks) if total_tasks > 0 else 0

    st.title("⭐ Product + Learning Task Board")
    st.markdown(f"### 🟩 STATUS SUMMARY — {percent_done}% complete")
    st.markdown(f"You have **{num_done} / {total_tasks}** tasks done.")
    st.markdown(
        f"- 🔴 TODO: **{num_todo}**  ·  🟡 IN PROGRESS: **{num_in_progress}**  ·  🟢 DONE: **{num_done}**"
    )
    st.subheader("Your tasks")

    filter_choice = st.radio(
        "Show",
        options=["TODO only", "IN_PROGRESS only", "DONE only", "All"],
        index=0,
        horizontal=True,
    )

    filtered_df = tasks_df
    if filter_choice == "TODO only":
        filtered_df = tasks_df[tasks_df["status"] == "TODO"]
    elif filter_choice == "IN_PROGRESS only":
        filtered_df = tasks_df[tasks_df["status"] == "IN_PROGRESS"]
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
        meta = EPIC_META.get(epic, {})
        icon = meta.get("icon", "🔹")
        section_label = meta.get("label", epic)
        expander_title = (
            f"{icon} {week_label} — {section_label}" if week_label else f"{icon} {section_label}"
        )
        with st.expander(expander_title, expanded=has_todo):
            for idx, row in epic_tasks.iterrows():
                current_status = row["status"] if row["status"] in STATUS_OPTIONS else "TODO"
                col_status, col_text = st.columns([0.2, 0.8])
                with col_status:
                    new_status = st.selectbox(
                        "Status",
                        STATUS_OPTIONS,
                        index=STATUS_OPTIONS.index(current_status),
                        key=f"status_{row['id']}",
                        label_visibility="collapsed",
                    )
                with col_text:
                    st.markdown(f"**{row['title']}**  {status_display(new_status)}")
                    desc = row.get("description", "") or ""
                    if desc:
                        st.caption(desc)
                if new_status != row["status"]:
                    tasks_df.loc[tasks_df["id"] == row["id"], "status"] = new_status
                    updated = True
                # Divider between tasks for visual separation
                if idx != epic_tasks.index[-1]:
                    st.markdown("<hr style='margin: 0.3rem 0;'/>", unsafe_allow_html=True)

    if updated:
        save_tasks(tasks_df)
        st.rerun()

    st.markdown("---")
    st.subheader("➕ Add a new task")
    title_input = st.text_input("New task title", key="new_task_title")

    existing_epics = sorted(tasks_df["epic"].dropna().unique().tolist())
    epic_choice = st.selectbox(
        "Epic",
        options=["(Choose epic)", "Create new epic"] + existing_epics,
        key="new_task_epic_choice",
    )
    new_epic_name = ""
    if epic_choice == "Create new epic":
        new_epic_name = st.text_input("New epic name", key="new_epic_name")

    description_input = st.text_area(
        "Description (optional)",
        key="new_task_description",
        height=80,
    )

    if st.button("Add task"):
        title = title_input.strip()
        if epic_choice == "Create new epic":
            epic = new_epic_name.strip()
        elif epic_choice == "(Choose epic)":
            epic = ""
        else:
            epic = epic_choice

        if not title:
            st.warning("Please enter a task title.")
        elif not epic:
            st.warning("Please choose or enter an epic.")
        else:
            next_id = int(tasks_df["id"].max()) + 1 if not tasks_df.empty else 1
            new_row = pd.DataFrame(
                [
                    {
                        "id": next_id,
                        "title": title,
                        "status": "TODO",
                        "epic": epic,
                        "description": description_input.strip(),
                    }
                ],
                columns=REQUIRED_COLUMNS,
            )
            tasks_df = pd.concat([tasks_df, new_row], ignore_index=True)
            save_tasks(tasks_df)
            st.success("Task added.")
            st.rerun()


if __name__ == "__main__":
    main()
