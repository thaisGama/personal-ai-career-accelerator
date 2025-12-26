import streamlit as st
from pathlib import Path

import src.agent.weekly_planner as weekly_planner


BASE_DIR = Path(__file__).resolve().parent


def ensure_data_dir():
    data_dir = BASE_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def run_planner(goal: str, hours_per_week: float, max_session_minutes: int, preferences: str, model: str):
    ensure_data_dir()

    result = weekly_planner.generate_and_save_week(
        goal=goal,
        time_per_week_hours=hours_per_week,
        max_session_minutes=max_session_minutes,
        preferences=preferences,
        model=model,
        base_dir=BASE_DIR,
    )

    # Your function returns raw_markdown that includes both plan + linkedin blocks
    raw_md = result.get("raw_markdown", "")

    # Use your helper to split (if it exists and matches your markers)
    try:
        plan_md, linkedin_md = weekly_planner.split_markdown_into_plan_and_linkedin(raw_md)
    except Exception:
        # Fallback: just show raw markdown if split fails
        plan_md, linkedin_md = raw_md, ""

    return result, plan_md, linkedin_md


st.set_page_config(page_title="AI Career Accelerator", layout="wide")

st.title("Personal AI Career Accelerator 🧠⚡")
st.caption("Generate a weekly micro-plan (30-minute chunks) and save it into your repo.")

with st.sidebar:
    st.header("Inputs")

    goal = st.text_input("Goal / focus", value="Learn embeddings + implement vector search memory (practical)")

    hours_per_week = st.slider("Time available per week (hours)", 0.5, 10.0, 2.0, 0.5)

    max_session_minutes = st.selectbox("Max session length (minutes)", [10, 15, 20, 30, 45, 60], index=3)

    preferences = st.text_area(
        "Preferences / constraints",
        value="Busy working mom. Prefer practical steps. Each task must fit in the max session time. Include deliverables and a LinkedIn draft.",
        height=120,
    )

    model = st.text_input("Model", value=getattr(weekly_planner, "DEFAULT_MODEL", "gpt-4.1-mini"))

    col1, col2 = st.columns(2)
    generate = col1.button("Generate plan", type="primary", use_container_width=True)
    clear = col2.button("Clear", use_container_width=True)

if clear:
    st.session_state.clear()
    st.rerun()

left, right = st.columns([2, 1], gap="large")

if generate:
    with st.spinner("Generating..."):
        result, plan_md, linkedin_md = run_planner(
            goal=goal,
            hours_per_week=hours_per_week,
            max_session_minutes=max_session_minutes,
            preferences=preferences,
            model=model,
        )

    st.session_state["result"] = result
    st.session_state["plan_md"] = plan_md
    st.session_state["linkedin_md"] = linkedin_md

with left:
    st.subheader("Plan preview")
    plan_md = st.session_state.get("plan_md")
    if plan_md:
        st.markdown(plan_md)
    else:
        st.info("Click **Generate plan** to create this week’s plan.")

    st.subheader("LinkedIn draft preview")
    linkedin_md = st.session_state.get("linkedin_md")
    if linkedin_md:
        st.markdown(linkedin_md)
    else:
        st.caption("No LinkedIn draft detected (or split failed).")

with right:
    st.subheader("Outputs")
    result = st.session_state.get("result")
    if result:
        st.success("Saved")
        st.write(f"**Plan:** `{result.get('plan_path')}`")
        st.write(f"**LinkedIn:** `{result.get('linkedin_path')}`")
        st.write(f"**Memory:** `{result.get('memory_path')}`")

        st.divider()
        st.subheader("Memory quick view")
        memory_path = Path(result.get("memory_path", BASE_DIR / "docs" / "memory.md"))
        if memory_path.exists():
            with st.expander("Show tail of memory.md"):
                txt = memory_path.read_text(encoding="utf-8")
                st.code(txt[-1500:])
        else:
            st.warning("memory.md not found yet.")
    else:
        st.caption("Run the planner to see saved paths and memory tail.")
