import json
import re
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

import src.agent.learning_check as learning_check
import src.agent.react_agent as react_agent
from src.agent.tools import (
    tool_load_tasks,
    tool_mark_done,
    tool_select_quiz_tasks,
    tool_update_tasks_from_quiz_results,
)
import src.agent.weekly_planner as weekly_planner


def parse_quiz_sections(text: str) -> dict:
    """
    Extract quiz sections by tags. Returns dict with keys:
    quiz, answer_key, rubric, follow_up, raw. Falls back gracefully.
    """

    def _between(src: str, start: str, end: str | None) -> str | None:
        start_idx = src.find(start)
        if start_idx == -1:
            return None
        start_idx += len(start)
        if end:
            end_idx = src.find(end, start_idx)
            if end_idx == -1:
                return src[start_idx:].strip()
            return src[start_idx:end_idx].strip()
        return src[start_idx:].strip()

    quiz = _between(text, "<<QUIZ>>", "<<ANSWER_KEY>>")
    if quiz is None:
        quiz = _between(text, "<<QUIZ>>", None)
    answer = _between(text, "<<ANSWER_KEY>>", "<<RUBRIC>>")
    rubric = _between(text, "<<RUBRIC>>", "<<FOLLOW_UP>>")
    follow = _between(text, "<<FOLLOW_UP>>", None)

    return {
        "quiz": quiz.strip() if quiz else None,
        "answer_key": answer.strip() if answer else None,
        "rubric": rubric.strip() if rubric else None,
        "follow_up": follow.strip() if follow else None,
        "raw": text,
    }


def parse_questions(quiz_text: str, task_ids: list[str] | None = None) -> tuple[str | None, list[dict]]:
    """
    Parse quiz text into (title, questions).
    Each question dict: {id: int, prompt, options, type}
    """
    lines = [line.strip() for line in quiz_text.splitlines() if line.strip()]

    title = None
    timebox = None
    start_idx = 0
    q_start_pattern = re.compile(r"^\s*[-*•]?\s*q?\s*([0-9]+)[\)\.:\-]\s*(.+)", flags=re.IGNORECASE)

    # Capture title/timebox until first question
    for idx, line in enumerate(lines):
        if q_start_pattern.match(line):
            start_idx = idx
            break
        if not title:
            title = line.strip("<> ")
        if line.lower().startswith("timebox"):
            timebox = line
    else:
        start_idx = len(lines)

    question_blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines[start_idx:]:
        if q_start_pattern.match(line) and current:
            question_blocks.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        question_blocks.append(current)

    questions: list[dict] = []
    opt_pattern = re.compile(r"^\s*[-*•]?\s*([A-Z])\)\s*(.+)")
    task_pattern = re.compile(r"\[task_id:([^\]]+)\]", flags=re.IGNORECASE)

    for block in question_blocks:
        if not block:
            continue
        stem_line = block[0]
        stem_match = q_start_pattern.match(stem_line)
        if not stem_match:
            continue
        qid_num = int(stem_match.group(1))
        prompt_parts = [stem_match.group(2).strip()]
        options: list[str] = []
        for line in block[1:]:
            opt_match = opt_pattern.match(line)
            if opt_match:
                options.append(f"{opt_match.group(1)}) {opt_match.group(2).strip()}")
            else:
                prompt_parts.append(line.strip())
        prompt = "\n".join([p for p in prompt_parts if p]).strip()
        task_id = None
        task_match = task_pattern.search(prompt)
        if task_match:
            task_id = task_match.group(1).strip()
            prompt = task_pattern.sub("", prompt).strip()
        lower_prompt = prompt.lower()

        if "true or false" in lower_prompt:
            qtype = "truefalse"
            options = ["True", "False"]
        elif options:
            qtype = "multi" if ("select all" in lower_prompt or "choose all" in lower_prompt) else "single"
        else:
            qtype = "open"

        questions.append({"id": qid_num, "prompt": prompt, "options": options, "type": qtype, "task_id": task_id})

    # Store timebox alongside title if available
    if timebox and title:
        title = f"{title} — {timebox}"
    elif timebox:
        title = timebox

    if task_ids:
        for idx, question in enumerate(questions):
            if question.get("task_id"):
                continue
            question["task_id"] = task_ids[idx % len(task_ids)]

    return title, questions


BASE_DIR = Path(__file__).resolve().parent


def ensure_data_dir():
    data_dir = BASE_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def append_quiz_results(results: list[dict], base_dir: Path) -> Path:
    data_dir = ensure_data_dir()
    path = data_dir / "quiz_results.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        for entry in results:
            handle.write(json.dumps(entry, ensure_ascii=True) + "\n")
    return path


def run_planner(
    goal: str,
    hours_per_week: float,
    max_session_minutes: int,
    preferences: str,
    intensity: str,
    background: str,
    roadmap_id: str,
    model: str,
    use_agent: bool,
    mock_actions_path: str | None,
):
    ensure_data_dir()

    if use_agent:
        preferences_payload = {
            "text": preferences or "",
            "target_level": intensity,
            "background": background or "",
            "roadmap_id": roadmap_id or "",
        }
        mock_path = Path(mock_actions_path) if mock_actions_path else None
        result = react_agent.run_weekly_planner_agent_react(
            goal=goal,
            hours_per_week=hours_per_week,
            max_session_minutes=max_session_minutes,
            preferences=preferences_payload,
            model=model,
            base_dir=BASE_DIR,
            mock_actions_path=mock_path,
        )
        plan_path_str = result.get("weekly_plan_path") or result.get("plan_path", "")
        linkedin_path_str = result.get("linkedin_path", "")
        plan_path = Path(plan_path_str) if plan_path_str else None
        linkedin_path = Path(linkedin_path_str) if linkedin_path_str else None
        plan_md = plan_path.read_text(encoding="utf-8") if plan_path and plan_path.is_file() else ""
        linkedin_md = (
            linkedin_path.read_text(encoding="utf-8") if linkedin_path and linkedin_path.is_file() else ""
        )
        if plan_path:
            result["plan_path"] = plan_path.as_posix()
        return result, plan_md, linkedin_md

    enriched_preferences = preferences or ""
    if intensity or background:
        enriched_preferences = (
            f"{enriched_preferences}\n\nLearning intensity: {intensity}\nBackground: {background or 'none'}"
        ).strip()

    result = weekly_planner.generate_and_save_week(
        goal=goal,
        time_per_week_hours=hours_per_week,
        max_session_minutes=max_session_minutes,
        preferences=enriched_preferences,
        model=model,
        base_dir=BASE_DIR,
    )

    raw_md = result.get("raw_markdown", "")

    try:
        memory_audit_block = raw_md.split("<<PLAN_MARKDOWN>>", 1)[0].strip()
        plan_text = weekly_planner.extract_between(raw_md, "<<PLAN_MARKDOWN>>", "<<END_PLAN>>")
        formatted = weekly_planner.format_weekly_plan(plan_text)
        if memory_audit_block:
            formatted = f"{memory_audit_block}\n\n{formatted}"
        plan_md, linkedin_md = weekly_planner.split_markdown_into_plan_and_linkedin(formatted)
    except Exception:
        plan_md, linkedin_md = raw_md, ""

    return result, plan_md, linkedin_md


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
    st.header("Weekly Planner inputs")
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
    generate = col1.button("Generate plan", type="primary", use_container_width=True)
    clear = col2.button("Clear planner", use_container_width=True)

planner_tab, quiz_tab, library_tab = st.tabs(["Weekly Planner", "Learning Check (Quiz)", "Learning Library"])

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
        effective_mock_path = mock_actions_path if use_agent_loop and use_mock_actions else None
        result, plan_md, linkedin_md = run_planner(
            goal=goal,
            hours_per_week=hours_per_week,
            max_session_minutes=max_session_minutes,
            preferences=preferences,
            intensity=learning_intensity,
            background=background,
            roadmap_id=roadmap_id,
            model=planner_model,
            use_agent=use_agent_loop,
            mock_actions_path=effective_mock_path,
        )

    st.session_state["planner_result"] = result
    st.session_state["planner_plan_md"] = plan_md
    st.session_state["planner_linkedin_md"] = linkedin_md

with planner_tab:
    st.markdown("## Weekly Planner")

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
                st.write(f"**Learning Unit:** `{result.get('learning_unit_path')}`")
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

            st.divider()
            if result.get("roadmap_path") or result.get("roadmap_total_hours"):
                st.subheader("Roadmap summary")
                if result.get("roadmap_path"):
                    st.write(f"**Roadmap:** `{result.get('roadmap_path')}`")
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
        generate_quiz = col_q1.button("Generate quiz", type="primary")
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
                    quiz_result = learning_check.generate_micro_quiz(
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
    evaluate_btn = st.button("Submit answers for evaluation", type="primary")
    st.markdown("</div>", unsafe_allow_html=True)

    if evaluate_btn:
        if not (quiz_md or "").strip():
            st.warning("Generate or paste a quiz first.")
        elif not (answers_payload or "").strip():
            st.warning("Please provide answers before evaluation.")
        else:
            with st.spinner("Evaluating..."):
                try:
                    eval_result = learning_check.evaluate_micro_quiz(
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
                        score = eval_result.get("score") or 0.0
                        score_ratio = float(score) / 10.0
                        timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
                        quiz_results = [
                            {
                                "task_id": task_id,
                                "score": score_ratio,
                                "notes": f"quiz_score={score_ratio:.2f} mastery={eval_result.get('mastery')}",
                                "timestamp": timestamp,
                            }
                            for task_id in st.session_state.get("quiz_task_ids", [])
                        ]
                        update_result = tool_update_tasks_from_quiz_results(
                            tasks_path=BASE_DIR / "data" / "tasks.csv",
                            quiz_results=quiz_results,
                            auto_close=False,
                        )
                        st.session_state["quiz_task_update"] = update_result
                        st.session_state["quiz_propose_done"] = update_result.get("propose_done", [])
                        tasks_payload = tool_load_tasks(path=BASE_DIR / "data" / "tasks.csv")
                        status_map = {
                            task.get("task_id"): task.get("status")
                            for task in tasks_payload.get("tasks", [])
                        }
                        st.session_state["quiz_task_statuses"] = [
                            (task_id, status_map.get(task_id, "UNKNOWN"))
                            for task_id in st.session_state.get("quiz_task_ids", [])
                        ]
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
            selected_name = st.selectbox("Choose a learning unit", list(options.keys()))
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
