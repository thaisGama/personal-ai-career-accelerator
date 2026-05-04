import json
import shutil
from datetime import datetime
from pathlib import Path

import streamlit as st

import src.agent.learning_check as learning_check
from src.agent.tools import (
    tool_mark_done,
    tool_select_quiz_tasks,
    tool_summarize_task_progress,
)
from src.agent.reset_utils import resolve_reset_paths, resolve_tasks_path
from src.agent.task_store import ensure_tasks_file
import src.agent.weekly_planner as weekly_planner
from src.core.io.quiz_results_store import append_quiz_results
from src.core.parsing.quiz_parsing import parse_questions, parse_quiz_sections
from src.core.services.planner_service import run_weekly_planner_service
from src.core.services.quiz_service import (
    evaluate_quiz_service,
    generate_quiz_service,
    update_tasks_from_quiz_service,
)


def _safe_delete_path(path: Path, base_dir: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, f"skip_missing:{path.as_posix()}"
    resolved = path.resolve()
    base_resolved = base_dir.resolve()
    if not str(resolved).startswith(str(base_resolved)):
        return False, f"skip_outside_base:{path.as_posix()}"
    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        return True, path.as_posix()
    except Exception as exc:
        return False, f"error:{path.as_posix()}:{exc}"


def _collect_reset_targets(scope: str, base_dir: Path) -> list[Path]:
    paths = resolve_reset_paths(base_dir)
    targets: list[Path] = [paths["tasks_path"]]
    if scope in {"Tasks + quiz history", "Everything"}:
        targets.extend([p for p in paths["quiz_paths"] if p.exists()])
    if scope in {"Tasks + memory", "Everything"}:
        targets.append(paths["memory_path"])
        targets.append(paths["memory_vectors_path"])
    if scope == "Everything":
        targets.extend(paths["outputs_dirs"])
    return targets


BASE_DIR = Path(__file__).resolve().parent


def _list_files_sorted(directory: Path, pattern: str) -> list[Path]:
    if not directory.exists():
        return []
    files = [path for path in directory.glob(pattern) if path.is_file()]
    return sorted(files, key=lambda path: path.stat().st_mtime, reverse=True)


def _format_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")


st.set_page_config(page_title="AI Career Accelerator", layout="wide")

st.title("Personal AI Career Accelerator 🧠⚡")
st.caption("Generate a weekly micro-plan (30-minute chunks) and save it into your repo.")
st.markdown(
    """
    <style>
    .card {
        padding: 1rem 1.2rem;
        border: 1px solid #e5e7eb;
        border-radius: 12px;
        background: #fbfbfc;
        margin-bottom: 1rem;
    }
    .card h3 {
        margin-top: 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Generate Plan inputs")
    offline_mode = st.toggle(
        "Offline / browse mode",
        value=st.session_state.get("offline_mode", False),
        key="offline_mode",
    )
    if offline_mode:
        st.info("Offline mode enabled. Browse plans/roadmaps; generation is disabled.")
    goal = st.text_input(
        "Goal / focus",
        value=st.session_state.get(
            "planner_goal",
            "Learn embeddings + implement vector search memory (practical)",
        ),
        key="planner_goal",
    )
    hours_per_week = st.slider(
        "Time available per week (hours)",
        0.5,
        10.0,
        st.session_state.get("planner_hours", 2.0),
        0.5,
        key="planner_hours",
    )
    max_session_minutes = st.selectbox(
        "Max session length (minutes)", [10, 15, 20, 30, 45, 60], index=3, key="planner_max_session"
    )
    preferences = st.text_area(
        "Preferences / constraints",
        value=st.session_state.get(
            "planner_preferences",
            "Busy working mom. Prefer practical steps. Each task must fit in the max session time. Include deliverables and a LinkedIn draft.",
        ),
        height=120,
        key="planner_preferences",
    )
    roadmap_id = st.text_input(
        "Roadmap ID (optional)",
        value=st.session_state.get("planner_roadmap_id", ""),
        key="planner_roadmap_id",
    )
    force_regenerate_roadmap = st.checkbox(
        "Force regenerate learning roadmap",
        value=st.session_state.get("force_regenerate_roadmap", False),
        key="force_regenerate_roadmap",
    )
    learning_intensity = st.selectbox(
        "Learning intensity",
        ["light", "medium", "hardcore"],
        index=["light", "medium", "hardcore"].index(st.session_state.get("planner_intensity", "medium")),
        key="planner_intensity",
    )
    background = st.text_area(
        "Background / constraints (optional)",
        value=st.session_state.get("planner_background", ""),
        height=80,
        key="planner_background",
    )
    planner_model = st.text_input(
        "Model", value=getattr(weekly_planner, "DEFAULT_MODEL", "gpt-4.1-mini"), key="planner_model"
    )
    use_agent_loop = st.checkbox(
        "Use agent loop (multi-step)",
        value=st.session_state.get("planner_use_agent", False),
        key="planner_use_agent",
    )
    enable_critic = st.checkbox(
        "Enable critic review",
        value=st.session_state.get("planner_enable_critic", False),
        key="planner_enable_critic",
    )
    use_mock_actions = st.checkbox(
        "Mock agent (use fixtures)",
        value=st.session_state.get("planner_use_mock", False),
        key="planner_use_mock",
        disabled=not use_agent_loop,
    )
    mock_actions_path = st.text_input(
        "Mock actions path",
        value=st.session_state.get("planner_mock_path", "tests/fixtures/react_actions.jsonl"),
        key="planner_mock_path",
        disabled=not use_agent_loop,
    )

    col1, col2 = st.columns(2)
    generate = col1.button(
        "Generate plan",
        type="primary",
        use_container_width=True,
        disabled=offline_mode,
    )
    clear = col2.button("Clear planner", use_container_width=True)
    st.caption("Generating will call the API.")

    st.divider()
    st.subheader("Reset progress")
    reset_scope = st.selectbox(
        "Reset scope",
        [
            "Tasks only",
            "Tasks + quiz history",
            "Tasks + memory",
            "Everything",
        ],
        key="reset_scope",
    )
    confirm_reset = st.checkbox(
        "I understand this will delete files",
        key="reset_confirm",
    )
    reset_targets = _collect_reset_targets(reset_scope, BASE_DIR)
    if reset_targets:
        st.caption("Will delete:")
        for target in reset_targets:
            st.code(target.as_posix())
    reset_now = st.button(
        "Reset progress now",
        use_container_width=True,
        disabled=not confirm_reset,
    )
    if reset_now:
        deleted: list[str] = []
        skipped: list[str] = []
        errors: list[str] = []
        base_dir = BASE_DIR
        tasks_path = resolve_tasks_path(base_dir)
        for target in reset_targets:
            ok, message = _safe_delete_path(target, base_dir)
            if ok:
                deleted.append(message)
            elif message.startswith("error:"):
                errors.append(message)
            else:
                skipped.append(message)
        ensure_tasks_file(tasks_path)
        deleted.append(tasks_path.as_posix())
        if errors:
            st.error("Reset completed with errors:\n" + "\n".join(errors))
        st.success("Deleted:\n" + "\n".join(deleted))
        if skipped:
            st.info("Skipped:\n" + "\n".join(skipped))

planner_tab, plans_tab, roadmaps_tab, quiz_tab, library_tab = st.tabs(
    ["Generate Plan", "View Plans", "Roadmaps", "Learning Check (Quiz)", "Learning Library"]
)
# Manual test: open Weekly Plans/Roadmaps tabs, load items into Planner, verify no generation unless Generate clicked.

if clear:
    for key in [
        "planner_result",
        "planner_plan_md",
        "planner_linkedin_md",
    ]:
        st.session_state.pop(key, None)
    st.rerun()

if generate:
    with st.spinner("Generating..."):
        active_roadmap_id = st.session_state.get("active_roadmap_id") or ""
        active_roadmap_path = st.session_state.get("active_roadmap_path") or ""
        effective_roadmap_id = roadmap_id or active_roadmap_id
        if not effective_roadmap_id and active_roadmap_path:
            active_path = Path(active_roadmap_path)
            if active_path.exists():
                effective_roadmap_id = active_path.stem

        effective_mock_path = mock_actions_path if use_agent_loop and use_mock_actions else None
        mock_path = Path(effective_mock_path) if effective_mock_path else None
        service_output = run_weekly_planner_service(
            goal=goal,
            hours_per_week=hours_per_week,
            max_session_minutes=max_session_minutes,
            preferences_text=preferences,
            intensity=learning_intensity,
            background=background,
            roadmap_id=effective_roadmap_id,
            force_regenerate_roadmap=force_regenerate_roadmap,
            model=planner_model,
            use_agent_loop=use_agent_loop,
            mock_actions_path=mock_path,
            enable_critic=enable_critic,
            base_dir=BASE_DIR,
        )
        result = service_output.get("result", {})
        plan_md = service_output.get("plan_md", "")
        linkedin_md = service_output.get("linkedin_md", "")

    st.session_state["planner_result"] = result
    st.session_state["planner_plan_md"] = plan_md
    st.session_state["planner_linkedin_md"] = linkedin_md

with planner_tab:
    st.markdown("## Generate Plan")

    col_left, col_right = st.columns([2.5, 1], gap="large")

    with col_left:
        st.markdown("### Plan preview")
        st.markdown('<div class="card">', unsafe_allow_html=True)
        plan_md = st.session_state.get("planner_plan_md")
        if plan_md:
            st.markdown(plan_md)
        else:
            st.info("Click **Generate plan** to create this week’s plan.")
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("### LinkedIn draft preview")
        st.markdown('<div class="card">', unsafe_allow_html=True)
        linkedin_md = st.session_state.get("planner_linkedin_md")
        if linkedin_md:
            st.markdown(linkedin_md)
        else:
            st.caption("No LinkedIn draft detected (or split failed).")
        st.markdown("</div>", unsafe_allow_html=True)

    with col_right:
        st.markdown("### Outputs")
        st.markdown('<div class="card">', unsafe_allow_html=True)
        result = st.session_state.get("planner_result")
        if result:
            st.success("Saved")
            st.write(f"**Plan:** `{result.get('plan_path')}`")
            st.write(f"**LinkedIn:** `{result.get('linkedin_path')}`")
            if result.get("learning_unit_path"):
                learning_unit_path = Path(result.get("learning_unit_path"))
                st.write(f"**Learning Unit:** `{learning_unit_path}`")
                if learning_unit_path.exists():
                    mtime = datetime.fromtimestamp(learning_unit_path.stat().st_mtime)
                    st.write(f"**Learning Unit modified:** {mtime.strftime('%Y-%m-%d %H:%M:%S')}")
            st.write(f"**Memory:** `{result.get('memory_path')}`")
            if result.get("next_task"):
                st.write(f"**Next task:** {result.get('next_task')}")
            if result.get("trace_path"):
                st.write(f"**Trace:** `{result.get('trace_path')}`")
                trace_path = Path(result.get("trace_path"))
                if trace_path.exists():
                    trace_data = None
                    try:
                        trace_data = json.loads(trace_path.read_text(encoding="utf-8"))
                    except Exception:
                        trace_data = None
                    if not result.get("weekly_plan_path") and trace_data:
                        if any(entry.get("tool_name") == "format_failure" for entry in trace_data):
                            st.error("Controller output was not valid JSON. See trace file.")
                    with st.expander("Recent trace steps"):
                        try:
                            if trace_data is None:
                                trace_data = json.loads(trace_path.read_text(encoding="utf-8"))
                            for entry in trace_data[-6:]:
                                st.write(
                                    f"{entry.get('step_name')} | {entry.get('tool_name')} | "
                                    f"{entry.get('tool_output_summary')}"
                                )
                        except Exception:
                            st.caption("Could not read trace details.")

            critic_report = result.get("critic_report")
            if result.get("critic_status") or critic_report:
                status = result.get("critic_status") or "UNKNOWN"
                st.write(f"**Critic:** {status}")
                if status == "FAIL" and critic_report:
                    with st.expander("Critic violations and patch list"):
                        violations = critic_report.get("violations", [])
                        patch_list = critic_report.get("patch_list", [])
                        if violations:
                            st.markdown("**Violations**")
                            for item in violations:
                                st.write(f"- [{item.get('id')}] {item.get('message')}")
                        if patch_list:
                            st.markdown("**Patch list**")
                            for item in patch_list:
                                st.write(f"- {item}")

            st.divider()
            if result.get("roadmap_path") or result.get("roadmap_total_hours"):
                st.subheader("Roadmap summary")
                if result.get("roadmap_path"):
                    st.write(f"**Roadmap:** `{result.get('roadmap_path')}`")
                    roadmap_path = Path(result.get("roadmap_path"))
                    if roadmap_path.exists():
                        mtime = datetime.fromtimestamp(roadmap_path.stat().st_mtime)
                        st.write(f"**Roadmap modified:** {mtime.strftime('%Y-%m-%d %H:%M:%S')}")
                if result.get("roadmap_total_hours") is not None:
                    st.write(f"**Total hours:** {result.get('roadmap_total_hours')}")
                estimated_weeks = result.get("roadmap_estimated_weeks") or {}
                if estimated_weeks:
                    st.write(
                        "**Estimated weeks (2/5/7 h/wk):** "
                        f"{estimated_weeks.get('2', '?')} / {estimated_weeks.get('5', '?')} / "
                        f"{estimated_weeks.get('7', '?')}"
                    )
                if result.get("roadmap_total_hours") and hours_per_week:
                    weeks_for_slider = float(result.get("roadmap_total_hours")) / float(hours_per_week)
                    st.write(f"**Estimated weeks at {hours_per_week}h/week:** {weeks_for_slider:.1f}")
                if result.get("roadmap_phase_count") is not None:
                    st.write(f"**Phases:** {result.get('roadmap_phase_count')}")
                if result.get("roadmap_current_phase") or result.get("roadmap_current_milestone"):
                    st.write(
                        f"**Current focus:** Phase {result.get('roadmap_current_phase')} | "
                        f"Milestone {result.get('roadmap_current_milestone')}"
                    )
                if result.get("roadmap_remaining_hours") is not None:
                    st.write(f"**Remaining hours:** {result.get('roadmap_remaining_hours')}")

                with st.expander("Debug roadmap progress"):
                    roadmap_id = result.get("roadmap_id") or ""
                    st.write(f"**Roadmap ID:** `{roadmap_id}`")
                    st.write(f"**Current phase:** {result.get('roadmap_current_phase')}")
                    st.write(f"**Current milestone:** {result.get('roadmap_current_milestone')}")
                    st.write(f"**Week number:** {result.get('roadmap_week_number')}")
                    st.write(f"**Completed hours:** {result.get('roadmap_completed_hours')}")
                    st.write(f"**Remaining hours:** {result.get('roadmap_remaining_hours')}")
                    st.write(f"**Completion mode:** {result.get('roadmap_completion_mode')}")
                    st.write(f"**Used hours/week:** {result.get('roadmap_used_hours_per_week')}")
                    st.write(f"**Debug notes:** {result.get('roadmap_debug_notes')}")
                    tasks_path = resolve_tasks_path(BASE_DIR)
                    task_summary = tool_summarize_task_progress(tasks_path=tasks_path)
                    st.write("**Task counts by status:**")
                    st.json(task_summary.get("counts_by_status", {}))
                    milestone_counts = result.get("roadmap_milestone_task_counts") or {}
                    if milestone_counts:
                        table_rows = []
                        for milestone_id in sorted(milestone_counts.keys())[:10]:
                            counts = milestone_counts[milestone_id] or {}
                            table_rows.append(
                                {
                                    "milestone_id": milestone_id,
                                    "total": counts.get("total", 0),
                                    "done": counts.get("done", 0),
                                    "validated": counts.get("validated", 0),
                                    "done_and_validated": counts.get("done_and_validated", 0),
                                }
                            )
                        st.write("**Milestone task counts (first 10):**")
                        st.table(table_rows)
                    else:
                        st.caption("No milestone task counts available.")
            else:
                st.subheader("Roadmap summary")
                st.caption("No roadmap loaded.")

            st.subheader("Memory quick view")
            raw_memory_path = result.get("memory_path")
            memory_path = Path(raw_memory_path) if raw_memory_path else (BASE_DIR / "docs" / "memory.md")
            if memory_path.is_file():
                with st.expander("Show tail of memory.md"):
                    txt = memory_path.read_text(encoding="utf-8")
                    st.code(txt[-1500:])
            else:
                st.warning("memory.md not found yet.")
        else:
            st.caption("Run the planner to see saved paths and memory tail.")
        st.markdown("</div>", unsafe_allow_html=True)

with plans_tab:
    st.markdown("## Saved Plans")
    plans_dir = BASE_DIR / "weekly_plans"
    plans = _list_files_sorted(plans_dir, "*.md")
    if not plans_dir.exists():
        st.info("weekly_plans/ not found yet.")
    elif not plans:
        st.info("No weekly plans found.")
    else:
        selected_path_str = st.session_state.get("weekly_plans_selected_path")
        selected_path = Path(selected_path_str) if selected_path_str else None
        options = plans
        selected_index = 0
        if selected_path and selected_path in options:
            selected_index = options.index(selected_path)
        plan_path = st.selectbox(
            "Choose a weekly plan",
            options,
            index=selected_index,
            format_func=lambda path: f"{_format_mtime(path)} — {path.name}",
            key="weekly_plans_select",
        )
        st.session_state["weekly_plans_selected_path"] = plan_path.as_posix()
        plan_md = plan_path.read_text(encoding="utf-8")
        st.caption(f"{plan_path.as_posix()} | modified {_format_mtime(plan_path)}")
        st.markdown(plan_md)
        if st.button("Load into Planner Preview", key="load_plan_into_preview"):
            st.session_state["planner_plan_md"] = plan_md
            st.session_state["planner_plan_path"] = plan_path.as_posix()
            st.session_state["planner_linkedin_md"] = ""
            st.success("Loaded into Planner preview.")

with roadmaps_tab:
    st.markdown("## Roadmaps")
    roadmaps_dir = BASE_DIR / "roadmaps"
    roadmaps = _list_files_sorted(roadmaps_dir, "*.json")
    if not roadmaps_dir.exists():
        st.info("roadmaps/ not found yet.")
    elif not roadmaps:
        st.info("No roadmap JSON files found.")
    else:
        selected_path_str = st.session_state.get("roadmaps_selected_path")
        selected_path = Path(selected_path_str) if selected_path_str else None
        options = roadmaps
        selected_index = 0
        if selected_path and selected_path in options:
            selected_index = options.index(selected_path)
        roadmap_path = st.selectbox(
            "Choose a roadmap",
            options,
            index=selected_index,
            format_func=lambda path: f"{_format_mtime(path)} — {path.name}",
            key="roadmaps_select",
        )
        st.session_state["roadmaps_selected_path"] = roadmap_path.as_posix()
        try:
            data = json.loads(roadmap_path.read_text(encoding="utf-8"))
        except Exception as exc:
            st.error(f"Failed to read roadmap JSON: {exc}")
            data = None

        if data:
            title = data.get("topic") or data.get("title") or data.get("goal") or roadmap_path.stem
            st.markdown(f"### {title}")
            target_level = data.get("target_level")
            if target_level:
                st.write(f"**Target level:** {target_level}")
            if data.get("estimated_weeks_at_hours_per_week"):
                weeks = data.get("estimated_weeks_at_hours_per_week", {})
                st.write(
                    "**Estimated weeks (2/5/7 h/wk):** "
                    f"{weeks.get('2', '?')} / {weeks.get('5', '?')} / {weeks.get('7', '?')}"
                )
            if data.get("total_estimated_hours") is not None:
                st.write(f"**Total estimated hours:** {data.get('total_estimated_hours')}")

            phases = data.get("phases", [])
            if phases:
                st.markdown("### Phases")
                for phase in phases:
                    phase_title = phase.get("title") or phase.get("phase_id") or "Phase"
                    phase_hours = phase.get("estimated_hours")
                    if phase_hours is not None:
                        st.markdown(f"**{phase_title}** — {phase_hours}h")
                    else:
                        st.markdown(f"**{phase_title}**")
                    milestones = phase.get("milestones", [])
                    if milestones:
                        for milestone in milestones:
                            milestone_id = milestone.get("milestone_id") or "M?"
                            milestone_title = milestone.get("title") or "Untitled milestone"
                            milestone_hours = milestone.get("estimated_hours")
                            if milestone_hours is not None:
                                st.markdown(f"- `{milestone_id}` — {milestone_title} ({milestone_hours}h)")
                            else:
                                st.markdown(f"- `{milestone_id}` — {milestone_title}")
                    else:
                        st.caption("No milestones listed for this phase.")
            else:
                st.caption("No phases found in this roadmap.")

            if st.button("Set as active roadmap", key="set_active_roadmap"):
                st.session_state["active_roadmap_path"] = roadmap_path.as_posix()
                st.session_state["active_roadmap_id"] = roadmap_path.stem
                st.session_state["planner_roadmap_id"] = roadmap_path.stem
                st.success("Active roadmap set.")

            with st.expander("Raw JSON"):
                st.json(data)
            st.caption(f"{roadmap_path.as_posix()} | modified {_format_mtime(roadmap_path)}")

with quiz_tab:
    st.markdown("## Learning Check (Quiz)")

    # Initialize quiz-related state
    st.session_state.setdefault("quiz_unlocked", False)

    with st.container():
        st.markdown('<div class="card">', unsafe_allow_html=True)
        quiz_topic = st.text_input("Topic", value=st.session_state.get("quiz_topic", "Embeddings basics"), key="quiz_topic")
        quiz_context = st.text_area(
            "Context / Notes (optional)",
            value=st.session_state.get("quiz_context", "Paste any notes or constraints to tailor the quiz."),
            height=120,
            key="quiz_context",
        )
        use_tasks = st.checkbox("Use tasks.csv", value=st.session_state.get("quiz_use_tasks", False), key="quiz_use_tasks")
        quiz_model = st.text_input(
            "Model", value=getattr(learning_check, "DEFAULT_MODEL", "gpt-4.1-mini"), key="quiz_model"
        )

        col_q1, col_q2 = st.columns(2)
        generate_quiz = col_q1.button("Generate quiz", type="primary", disabled=offline_mode)
        clear_quiz = col_q2.button("Clear quiz state")
        st.markdown("</div>", unsafe_allow_html=True)

    if clear_quiz:
        for key in [
            "quiz_markdown",
            "quiz_path",
            "quiz_eval",
            "quiz_eval_block",
            "quiz_eval_score",
            "quiz_eval_mastery",
            "quiz_eval_decision",
            "quiz_unlocked",
            "quiz_answers_fallback",
            "quiz_selected_tasks",
            "quiz_task_ids",
            "quiz_propose_done",
            "quiz_task_statuses",
        ]:
            st.session_state.pop(key, None)
        # clear individual answer widgets
        for k in list(st.session_state.keys()):
            if k.startswith("quiz_answer_"):
                st.session_state.pop(k)
        st.rerun()

    selected_tasks = []
    tasks_context = ""
    task_ids = []
    if use_tasks:
        selection = tool_select_quiz_tasks(tasks_path=BASE_DIR / "data" / "tasks.csv", n=3)
        selected_tasks = selection.get("selected_tasks", [])
        task_ids = [task.get("task_id", "") for task in selected_tasks if task.get("task_id")]
        st.session_state["quiz_selected_tasks"] = selected_tasks
        st.session_state["quiz_task_ids"] = task_ids
        if selected_tasks:
            lines = [f"- {task.get('task_id')}: {task.get('title')} ({task.get('topic')})" for task in selected_tasks]
            tasks_context = "Tasks for quiz:\n" + "\n".join(lines)
            st.caption("Using tasks.csv to focus the quiz on open tasks.")
        else:
            st.warning("No open tasks found in tasks.csv. Quiz will use the topic instead.")
    else:
        st.session_state.pop("quiz_selected_tasks", None)
        st.session_state.pop("quiz_task_ids", None)
        st.session_state.pop("quiz_task_statuses", None)

    if generate_quiz:
        if not quiz_topic.strip():
            st.warning("Please provide a topic before generating a quiz.")
        else:
            with st.spinner("Generating quiz..."):
                try:
                    combined_context = quiz_context
                    if tasks_context:
                        combined_context = f"{combined_context}\n\n{tasks_context}".strip()
                    quiz_result = generate_quiz_service(
                        topic=quiz_topic,
                        context_text=combined_context,
                        tasks=selected_tasks if selected_tasks else None,
                        model=quiz_model,
                        base_dir=BASE_DIR,
                    )
                    st.session_state["quiz_markdown"] = quiz_result["quiz_markdown"]
                    st.session_state["quiz_path"] = quiz_result["quiz_path"]
                    st.success(f"Quiz saved to `{quiz_result['quiz_path']}`")
                    st.session_state["quiz_unlocked"] = False
                    for k in list(st.session_state.keys()):
                        if k.startswith("quiz_answer_"):
                            st.session_state.pop(k)
                    st.session_state.pop("quiz_eval_block", None)
                except Exception as exc:  # pragma: no cover - runtime path
                    st.error(f"Failed to generate quiz: {exc}")

    quiz_md = st.session_state.get("quiz_markdown")
    sections = parse_quiz_sections(quiz_md) if quiz_md else {}

    if quiz_md and sections.get("quiz"):
        title, questions = parse_questions(sections["quiz"], task_ids=st.session_state.get("quiz_task_ids"))

        st.markdown("### Quiz preview")
        st.markdown('<div class="card">', unsafe_allow_html=True)
        if title:
            st.markdown(f"**{title}**")
        st.markdown("**Timebox:** 5–7 minutes")
        st.markdown("</div>", unsafe_allow_html=True)

        if questions:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            for q in questions:
                st.markdown(f"### Q{q['id']}")
                st.markdown(q["prompt"])
                key = f"quiz_answer_{q['id']}"
                if q["type"] == "single":
                    st.radio(
                        "Select one",
                        options=q["options"],
                        key=key,
                        label_visibility="collapsed",
                    )
                elif q["type"] == "multi":
                    st.multiselect(
                        "Select all that apply",
                        options=q["options"],
                        key=key,
                        label_visibility="collapsed",
                    )
                elif q["type"] == "truefalse":
                    st.radio("True or False", options=["True", "False"], key=key, label_visibility="collapsed")
                else:
                    st.text_area("Answer", key=key, height=100, label_visibility="collapsed")
                st.markdown("---")
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.warning("Could not parse questions. Showing raw quiz content.")
            st.code(sections["quiz"])
            st.text_area("Use fallback answers box", key="quiz_answers_fallback", height=180)

        with st.expander("How you'll be evaluated (rubric)", expanded=False):
            rubric_md = sections.get("rubric")
            if rubric_md:
                st.markdown(rubric_md)
            else:
                st.caption("No rubric found.")

        answer_key_md = sections.get("answer_key")
        if st.session_state.get("quiz_unlocked"):
            with st.expander("Show answer key", expanded=False):
                if answer_key_md:
                    st.markdown(answer_key_md)
                else:
                    st.caption("No answer key found.")
        else:
            with st.expander("Show answer key", expanded=False):
                st.info("Answer key unlocks after you submit your answers (or click Unlock).")

        follow_md = sections.get("follow_up")
        if follow_md:
            with st.expander("Follow-up / Next practice", expanded=False):
                st.markdown(follow_md)

        quiz_saved_path = st.session_state.get("quiz_path")
        if quiz_saved_path:
            st.caption(f"Saved at: `{quiz_saved_path}`")
    elif quiz_md:
        st.warning("Could not parse quiz sections; showing raw quiz content.")
        st.code(quiz_md)
        st.text_area("Use fallback answers box", key="quiz_answers_fallback", height=180)
    else:
        st.caption("Generate a quiz to see it here.")

    answers_payload = None
    questions_for_eval = []
    if quiz_md and sections.get("quiz"):
        _, questions_for_eval = parse_questions(sections["quiz"], task_ids=st.session_state.get("quiz_task_ids"))
        if questions_for_eval:
            payload_lines = []
            for q in questions_for_eval:
                key = f"quiz_answer_{q['id']}"
                val = st.session_state.get(key)
                if isinstance(val, list):
                    val = ", ".join(val)
                payload_lines.append(f"Q{q['id']}: {val if val else 'Not answered'}")
            answers_payload = "\n".join(payload_lines)
    if answers_payload is None:
        answers_payload = st.session_state.get("quiz_answers_fallback", "")

    st.markdown("### Submit answers")
    st.markdown('<div class="card">', unsafe_allow_html=True)
    evaluate_btn = st.button("Submit answers for evaluation", type="primary", disabled=offline_mode)
    st.markdown("</div>", unsafe_allow_html=True)

    if evaluate_btn:
        if not (quiz_md or "").strip():
            st.warning("Generate or paste a quiz first.")
        elif not (answers_payload or "").strip():
            st.warning("Please provide answers before evaluation.")
        else:
            with st.spinner("Evaluating..."):
                try:
                    eval_result = evaluate_quiz_service(
                        topic=quiz_topic,
                        quiz_markdown=quiz_md,
                        learner_answers=answers_payload,
                        model=quiz_model,
                    )
                    st.session_state["quiz_eval"] = eval_result
                    st.session_state["quiz_eval_block"] = eval_result.get("eval_block")
                    st.session_state["quiz_eval_score"] = eval_result.get("score")
                    st.session_state["quiz_eval_mastery"] = eval_result.get("mastery")
                    st.session_state["quiz_eval_decision"] = eval_result.get("move_on_decision")
                    st.session_state["quiz_unlocked"] = True
                    if use_tasks and st.session_state.get("quiz_task_ids"):
                        task_ids_for_update = st.session_state.get("quiz_task_ids", [])
                        update_summary = update_tasks_from_quiz_service(
                            task_ids=task_ids_for_update,
                            eval_result=eval_result,
                            tasks_path=BASE_DIR / "data" / "tasks.csv",
                            auto_close=False,
                        )
                        update_result = update_summary.get("update_result", {})
                        quiz_results = update_summary.get("quiz_results", [])
                        st.session_state["quiz_task_update"] = update_result
                        st.session_state["quiz_propose_done"] = update_summary.get("propose_done", [])
                        st.session_state["quiz_task_statuses"] = update_summary.get("statuses", [])
                        append_quiz_results(quiz_results, base_dir=BASE_DIR)
                except Exception as exc:  # pragma: no cover - runtime path
                    st.error(f"Failed to evaluate answers: {exc}")

    eval_block = st.session_state.get("quiz_eval_block")
    if eval_block:
        st.markdown("### Evaluation")
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown(eval_block)
        score = st.session_state.get("quiz_eval_score")
        mastery = st.session_state.get("quiz_eval_mastery")
        decision = st.session_state.get("quiz_eval_decision")
        st.caption(
            f"Score: {score if score is not None else 'n/a'} | "
            f"Mastery: {mastery or 'n/a'} | Move-on decision: {decision or 'n/a'}"
        )
        task_update = st.session_state.get("quiz_task_update")
        if task_update:
            st.caption(
                f"Task updates: {task_update.get('updated_count', 0)} "
                f"(proposed DONE: {len(task_update.get('propose_done', []))})"
            )
            statuses = st.session_state.get("quiz_task_statuses", [])
            if statuses:
                st.markdown("Updated task statuses:")
                for task_id, status in statuses:
                    st.markdown(f"- `{task_id}` → **{status}**")

        if st.button("Append mastery to memory.md"):
            try:
                memory_path = learning_check.append_mastery_to_memory(
                    topic=quiz_topic, eval_block=eval_block, base_dir=BASE_DIR
                )
                st.success(f"Appended mastery summary to `{memory_path}`")
            except Exception as exc:  # pragma: no cover - runtime path
                st.error(f"Failed to append to memory: {exc}")
        propose_done = st.session_state.get("quiz_propose_done", [])
        if propose_done:
            st.divider()
            st.caption("Proposed DONE tasks (approve to mark complete):")
            selected_done = []
            for task_id in propose_done:
                if st.checkbox(f"Mark {task_id} as DONE", key=f"done_{task_id}"):
                    selected_done.append(task_id)
            if st.button("Confirm DONE updates"):
                if selected_done:
                    result = tool_mark_done(tasks_path=BASE_DIR / "data" / "tasks.csv", task_ids=selected_done)
                    st.success(f"Marked {result.get('updated_count', 0)} tasks as DONE.")
                else:
                    st.info("No tasks selected for DONE.")
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        if st.button("Unlock answers (manual)"):
            st.session_state["quiz_unlocked"] = True

with library_tab:
    st.markdown("## Learning Library")
    refresh = st.button("Refresh library")
    if refresh:
        st.session_state["learning_library_refresh"] = st.session_state.get("learning_library_refresh", 0) + 1
        st.rerun()

    library_dir = BASE_DIR / "docs" / "learning_units"
    if not library_dir.exists():
        st.info("No learning units saved yet. Generate a weekly plan to create one.")
    else:
        files = sorted(
            [path for path in library_dir.glob("*.md") if path.is_file()],
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if not files:
            st.info("No learning units found in docs/learning_units.")
        else:
            options = {path.name: path for path in files}
            refresh_token = st.session_state.get("learning_library_refresh", 0)
            selected_name = st.selectbox(
                "Choose a learning unit",
                list(options.keys()),
                key=f"learning_unit_select_{refresh_token}",
            )
            selected_path = options.get(selected_name)
            if selected_path:
                content = selected_path.read_text(encoding="utf-8")
                title = None
                for line in content.splitlines():
                    if line.startswith("# "):
                        title = line[2:].strip()
                        break
                if title:
                    st.markdown(f"### {title}")

                sections = []
                current_title = None
                current_lines = []
                for line in content.splitlines():
                    if line.startswith("## "):
                        if current_title:
                            sections.append((current_title, "\n".join(current_lines).strip()))
                        current_title = line[3:].strip()
                        current_lines = []
                    else:
                        current_lines.append(line)
                if current_title:
                    sections.append((current_title, "\n".join(current_lines).strip()))

                if sections:
                    for section_title, body in sections:
                        with st.expander(section_title, expanded=False):
                            st.markdown(body or "_No content_")
                else:
                    st.markdown(content)
