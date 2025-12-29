import json
import re
from pathlib import Path

import streamlit as st

import src.agent.learning_check as learning_check
import src.agent.react_agent as react_agent
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


def parse_questions(quiz_text: str) -> tuple[str | None, list[dict]]:
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
        lower_prompt = prompt.lower()

        if "true or false" in lower_prompt:
            qtype = "truefalse"
            options = ["True", "False"]
        elif options:
            qtype = "multi" if ("select all" in lower_prompt or "choose all" in lower_prompt) else "single"
        else:
            qtype = "open"

        questions.append({"id": qid_num, "prompt": prompt, "options": options, "type": qtype})

    # Store timebox alongside title if available
    if timebox and title:
        title = f"{title} — {timebox}"
    elif timebox:
        title = timebox

    return title, questions


BASE_DIR = Path(__file__).resolve().parent


def ensure_data_dir():
    data_dir = BASE_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def run_planner(
    goal: str,
    hours_per_week: float,
    max_session_minutes: int,
    preferences: str,
    model: str,
    use_agent: bool,
    mock_actions_path: str | None,
):
    ensure_data_dir()

    if use_agent:
        preferences_payload = {"text": preferences or ""}
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

planner_tab, quiz_tab = st.tabs(["Weekly Planner", "Learning Check (Quiz)"])

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
                            for entry in trace_data[-3:]:
                                st.write(
                                    f"{entry.get('step_name')} | {entry.get('tool_name')} | "
                                    f"{entry.get('tool_output_summary')}"
                                )
                        except Exception:
                            st.caption("Could not read trace details.")

            st.divider()
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
        ]:
            st.session_state.pop(key, None)
        # clear individual answer widgets
        for k in list(st.session_state.keys()):
            if k.startswith("quiz_answer_"):
                st.session_state.pop(k)
        st.rerun()

    if generate_quiz:
        if not quiz_topic.strip():
            st.warning("Please provide a topic before generating a quiz.")
        else:
            with st.spinner("Generating quiz..."):
                try:
                    quiz_result = learning_check.generate_micro_quiz(
                        topic=quiz_topic,
                        context_text=quiz_context,
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
        title, questions = parse_questions(sections["quiz"])

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
        _, questions_for_eval = parse_questions(sections["quiz"])
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

        if st.button("Append mastery to memory.md"):
            try:
                memory_path = learning_check.append_mastery_to_memory(
                    topic=quiz_topic, eval_block=eval_block, base_dir=BASE_DIR
                )
                st.success(f"Appended mastery summary to `{memory_path}`")
            except Exception as exc:  # pragma: no cover - runtime path
                st.error(f"Failed to append to memory: {exc}")
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        if st.button("Unlock answers (manual)"):
            st.session_state["quiz_unlocked"] = True
