"""Weekly planner agent utilities for generating learning plans via OpenAI."""

from __future__ import annotations

import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Tuple

from openai import OpenAI

from .prompts import render_prompt
from .learning_progress_store import append_week_from_plan, parse_days_from_plan, resolve_learning_progress_path
from .learning_purpose import purpose_context
from .memory.vector_store import LocalVectorStore
from .task_store import TaskProgressSummary, load_tasks, summarize_task_progress, upsert_tasks_from_plan

DEFAULT_MODEL = os.getenv("PLANNER_MODEL", "gpt-4o-mini")
MAX_TOKENS = int(os.getenv("PLANNER_MAX_TOKENS", "4500"))
PLAN_MAX_TOKENS = int(os.getenv("PLANNER_PLAN_MAX_TOKENS", "2200"))
UNIT_MAX_TOKENS = int(os.getenv("PLANNER_UNIT_MAX_TOKENS", "2800"))


def build_weekly_planner_prompt(
    goal: str,
    time_per_week_hours: float,
    max_session_minutes: int,
    preferences: str | None,
    memory_context: str,
    memory_used: bool,
    memory_source: str,
    memory_char_count: int,
    task_progress: TaskProgressSummary | None = None,
    roadmap_context: str | None = None,
    roadmap_progress: str | None = None,
    week_number: int | None = None,
    target_level: str | None = None,
    background: str | None = None,
    learner_setup: dict | None = None,
) -> Tuple[str, str]:
    """Construct system and user prompts for the weekly planner agent."""
    # Plan prompt stays compact; learning unit has its own dedicated prompt.
    system_prompt = render_prompt(
        "weekly_plan.system",
        MEMORY_USED='YES' if memory_used else 'NO',
        MEMORY_SOURCE=memory_source,
        MEMORY_CHAR_COUNT=memory_char_count,
        WEEK_NUMBER=week_number or 1,
    )

    task_block = ""
    if task_progress:
        open_tasks = task_progress.open_tasks[:5]
        open_lines = []
        for task in open_tasks:
            open_lines.append(
                f"- {task.get('title')} (id={task.get('task_id')}, "
                f"status={task.get('status')}, priority={task.get('priority')}, "
                f"evidence={task.get('evidence_score')})"
            )
        weak_topics = ", ".join(task_progress.weak_topics) if task_progress.weak_topics else "None"
        completed = (
            "\n".join([f"- {title}" for title in task_progress.completed_last_week])
            if task_progress.completed_last_week
            else "None"
        )
        task_block = render_prompt(
            "weekly_plan.task_progress",
            open_tasks='\n'.join(open_lines) if open_lines else 'None',
            weak_topics=weak_topics,
            completed=completed,
        )

    roadmap_block = ""
    if roadmap_progress:
        roadmap_block += f"\n{roadmap_progress}\n"
    if roadmap_context:
        roadmap_block += f"\n{roadmap_context}\n"

    user_prompt = render_prompt(
        "weekly_plan.user",
        goal=goal,
        time_per_week_hours=time_per_week_hours,
        max_session_minutes=max_session_minutes,
        target_level=target_level or 'medium',
        background=background or 'none',
        preferences=preferences or 'none',
        memory_context=memory_context,
        task_block=task_block,
        roadmap_block=roadmap_block,
    )

    return system_prompt, user_prompt + purpose_context(learner_setup)


def build_learning_unit_prompt(
    goal: str,
    preferences: str | None,
    memory_context: str,
    roadmap_tags: str | None,
    roadmap_context: str | None,
    plan_context: str | None,
    target_level: str | None = None,
    background: str | None = None,
    target_role: str | None = None,
    learner_setup: dict | None = None,
) -> Tuple[str, str]:
    """Construct system and user prompts for the learning unit generator."""
    effective_role = target_role or (learner_setup["goal"] if learner_setup else "AI Engineer / AI Generalist")
    system_prompt = render_prompt("learning_unit.system")

    roadmap_line = f"Roadmap tags from the plan: {roadmap_tags}" if roadmap_tags else "Roadmap tags from the plan: none"
    roadmap_context_block = roadmap_context or "Roadmap context: not provided."
    plan_context_block = plan_context or "Plan context: not provided."
    user_prompt = render_prompt(
        "learning_unit.user",
        goal=goal,
        effective_role=effective_role,
        target_level=target_level or 'medium',
        background=background or 'none',
        preferences=preferences or 'none',
        roadmap_line=roadmap_line,
        roadmap_context_block=roadmap_context_block,
        plan_context_block=plan_context_block,
        memory_context=memory_context or 'none',
    )

    return system_prompt, user_prompt + purpose_context(learner_setup)


def call_llm(
    system_prompt: str,
    user_prompt: str,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.5,
    max_tokens: int | None = None,
) -> str:
    """Call OpenAI's chat completions API and return the assistant markdown string."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set.")

    token_limit = max_tokens or MAX_TOKENS
    if model == "gpt-6-luna":
        # Luna permits temperature with reasoning disabled; retain the caller's budget.
        model_params = {"reasoning_effort": "none", "max_completion_tokens": token_limit}
    else:
        model_params = {"max_tokens": token_limit}

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            **model_params,
        )
    except Exception as exc:  # pragma: no cover - network/API path
        raise RuntimeError(f"Failed to call OpenAI chat completion: {exc}") from exc

    if not response or not response.choices:
        raise RuntimeError("OpenAI chat completion returned no choices.")

    message = response.choices[0].message.content
    if not message:
        raise RuntimeError("OpenAI chat completion returned empty content.")

    usage = getattr(response, "usage", None)
    if usage is not None:
        try:
            print(
                f"[WeeklyPlanner] Token usage — model: {response.model}, prompt: {usage.prompt_tokens}, "
                f"completion: {usage.completion_tokens}, total: {usage.total_tokens}"
            )
        except Exception:
            pass

    return message


def extract_between(text: str, start: str, end: str) -> str:
    """Return the substring between the given markers, or the stripped text if markers are missing."""
    start_idx = text.find(start)
    end_idx = text.find(end)
    if start_idx == -1 or end_idx == -1:
        return text.strip()
    start_idx += len(start)
    return text[start_idx:end_idx].strip()


def extract_learning_unit(text: str) -> str:
    """Extract the learning unit markdown if present, otherwise return an empty string."""
    if "<<LEARNING_UNIT>>" not in text or "<<END_LEARNING_UNIT>>" not in text:
        return ""
    return extract_between(text, "<<LEARNING_UNIT>>", "<<END_LEARNING_UNIT>>")


def _extract_roadmap_tags(plan_markdown: str) -> str | None:
    phase_tags = re.findall(r"\[phase:([^\]]+)\]", plan_markdown, flags=re.IGNORECASE)
    milestone_tags = re.findall(r"\[milestone:([^\]]+)\]", plan_markdown, flags=re.IGNORECASE)
    depth_tags = re.findall(r"\[depth:([^\]]+)\]", plan_markdown, flags=re.IGNORECASE)
    phases = sorted({tag.strip() for tag in phase_tags if tag.strip()})
    milestones = sorted({tag.strip() for tag in milestone_tags if tag.strip()})
    depths = sorted({tag.strip() for tag in depth_tags if tag.strip()})
    if not phases and not milestones and not depths:
        return None
    parts = []
    if phases:
        parts.append(f"phases={', '.join(phases)}")
    if milestones:
        parts.append(f"milestones={', '.join(milestones)}")
    if depths:
        parts.append(f"depths={', '.join(depths)}")
    return "; ".join(parts)


def _truncate_text(text: str, max_chars: int = 1200) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "..."


def format_weekly_plan(raw_text: str) -> str:
    """Clean the raw LLM response and ensure it is plain Markdown."""
    content = raw_text.strip()

    # Remove wrapping code fences if present.
    if content.startswith("```"):
        # Remove first fence
        content = content.split("```", 1)[-1].strip()
    if content.endswith("```"):
        content = content.rsplit("```", 1)[0].strip()

    # Ensure there is a top-level Week heading.
    if not content.lstrip().lower().startswith("# week"):
        content = "# Week Plan\n\n" + content

    return content


def remove_duplicate_daily_breakdown_sections(markdown: str) -> str:
    """Keep one Daily Breakdown heading while preserving later section content."""
    daily_heading = re.compile(
        r"^[ \t]*(?:#{1,6}[ \t]*)?(?:[^\w\s#]+[ \t]*)?Daily Breakdown[ \t]*$",
        flags=re.IGNORECASE,
    )
    day_line = re.compile(r"^[ \t]*(?:[-*][ \t]*)?(Day\s+\d+:[ \t]*.+)$", flags=re.IGNORECASE)
    lines = markdown.splitlines()
    cleaned_lines: list[str] = []
    seen_daily_breakdown = False
    seen_day_lines: set[str] = set()

    for line in lines:
        if daily_heading.match(line):
            if seen_daily_breakdown:
                continue
            seen_daily_breakdown = True
        day_match = day_line.match(line)
        if day_match:
            normalized_day_line = re.sub(r"\s+", " ", day_match.group(1).strip()).lower()
            if normalized_day_line in seen_day_lines:
                continue
            seen_day_lines.add(normalized_day_line)
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


def enforce_week_heading(markdown: str, week_number: int) -> str:
    heading = f"# Week {week_number} Learning Plan"
    lines = markdown.splitlines()
    if not lines:
        return heading
    if lines[0].lstrip().startswith("#"):
        lines[0] = heading
        return "\n".join(lines)
    return "\n".join([heading, ""] + lines)


def check_learning_unit_quality(md: str) -> dict:
    issues: list[str] = []
    missing_definitions: list[str] = []

    def _has_section(label: str) -> bool:
        return re.search(rf"^##\s+{re.escape(label)}\b", md, flags=re.IGNORECASE | re.MULTILINE) is not None

    def _section_text(label: str) -> str:
        pattern = re.compile(rf"^##\s+{re.escape(label)}\b.*$", flags=re.IGNORECASE | re.MULTILINE)
        match = pattern.search(md)
        if not match:
            return ""
        start = match.end()
        next_match = re.search(r"^##\s+", md[start:], flags=re.MULTILINE)
        end = start + next_match.start() if next_match else len(md)
        return md[start:end].strip()

    required_sections = [
        "Decision Lens",
        "Worked Examples",
        "Mini-Project Blueprint",
    ]
    for section in required_sections:
        if not _has_section(section):
            issues.append(f"missing_section:{section}")

    exercise_marker = re.search(r"\bexercise\b|\btry this\b", md, flags=re.IGNORECASE)
    self_check_marker = re.search(r"\bself-check\b|\brubric\b|\bchecklist\b", md, flags=re.IGNORECASE)
    has_exercise_and_selfcheck = bool(exercise_marker and self_check_marker)
    if not has_exercise_and_selfcheck:
        issues.append("missing_exercise_or_selfcheck")

    worked_examples = _section_text("Worked Examples")
    example_progression_ok = True
    if not re.search(r"Example\s+1", worked_examples, flags=re.IGNORECASE):
        example_progression_ok = False
    if not re.search(r"Example\s+2", worked_examples, flags=re.IGNORECASE):
        example_progression_ok = False
    if not re.search(r"Example\s+3", worked_examples, flags=re.IGNORECASE):
        example_progression_ok = False
    if example_progression_ok:
        ex1 = re.split(r"Example\s+2", worked_examples, flags=re.IGNORECASE)[0]
        ex2_parts = re.split(r"Example\s+2", worked_examples, flags=re.IGNORECASE)
        ex2 = ex2_parts[1] if len(ex2_parts) > 1 else ""
        ex2 = re.split(r"Example\s+3", ex2, flags=re.IGNORECASE)[0]
        ex3_parts = re.split(r"Example\s+3", worked_examples, flags=re.IGNORECASE)
        ex3 = ex3_parts[1] if len(ex3_parts) > 1 else ""

        if not re.search(r"\b(simple|naive|baseline)\b", ex1, flags=re.IGNORECASE):
            example_progression_ok = False
        if not re.search(r"\b(template|format|steps|schema|structured)\b", ex2, flags=re.IGNORECASE):
            example_progression_ok = False
        if not re.search(
            r"\b(constraints|evaluation|debug|checklist|tests|rubric)\b", ex3, flags=re.IGNORECASE
        ):
            example_progression_ok = False
    if not example_progression_ok:
        issues.append("example_progression_failed")

    decision_lens_text = _section_text("Decision Lens")
    decision_lens_ok = True
    use_count = 0
    dont_count = 0
    mode = None
    for line in decision_lens_text.splitlines():
        line_stripped = line.strip()
        if line_stripped.lower().startswith("- use when") or line_stripped.lower().startswith("use when"):
            mode = "use"
            continue
        if line_stripped.lower().startswith("- don't use when") or line_stripped.lower().startswith("don't use when"):
            mode = "dont"
            continue
        if line_stripped.startswith("-"):
            if mode == "use":
                use_count += 1
            elif mode == "dont":
                dont_count += 1
    boundary_markers = [
        "deterministic",
        "compliance",
        "hard guarantee",
        "hard guarantees",
        "requires training",
        "use a",
        "use an",
        "alternative",
        "script",
    ]
    boundary_ok = any(marker in decision_lens_text.lower() for marker in boundary_markers)
    if use_count < 2 or dont_count < 2 or not boundary_ok:
        decision_lens_ok = False
    if not decision_lens_ok:
        issues.append("decision_lens_not_discriminative")

    def _collect_named_terms(text: str) -> list[str]:
        terms: set[str] = set()
        for match in re.findall(r"\b\w+-shot\b", text, flags=re.IGNORECASE):
            terms.add(match)
        for match in re.findall(
            r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b",
            text,
        ):
            terms.add(match)
        for match in re.findall(
            r"\b[\w-]*(prompting|strategy|pattern|framework|heuristic|protocol|pipeline|approach|baseline)\b",
            text,
            flags=re.IGNORECASE,
        ):
            terms.add(match)
        return sorted(terms)

    def _has_definition(term: str, text: str) -> bool:
        term_re = re.compile(rf"\b{re.escape(term)}\b", flags=re.IGNORECASE)
        for paragraph in re.split(r"\n\s*\n", text):
            if term_re.search(paragraph) and re.search(
                r"\b(means|refers to|defined as|is)\b",
                paragraph,
                flags=re.IGNORECASE,
            ):
                return True
        return False

    operational_text = "\n".join(
        [
            _section_text("Operational Playbook"),
            worked_examples,
        ]
    )
    intro_text = md.split("## Operational Playbook")[0] if "## Operational Playbook" in md else md
    for term in _collect_named_terms(md):
        term_re = re.compile(rf"\b{re.escape(term)}\b", flags=re.IGNORECASE)
        if not term_re.search(operational_text):
            continue
        operational_idx = term_re.search(operational_text).start()
        if _has_definition(term, intro_text):
            continue
        if _has_definition(term, operational_text[:operational_idx + len(term) + 80]):
            continue
        missing_definitions.append(term)

    if missing_definitions:
        issues.append("missing_definitions")

    ok = not issues
    return {
        "ok": ok,
        "issues": issues,
        "missing_definitions": missing_definitions,
        "example_progression_ok": example_progression_ok,
        "decision_lens_ok": decision_lens_ok,
        "has_exercise_and_selfcheck": has_exercise_and_selfcheck,
    }


def save_weekly_plan(
    markdown: str, output_dir: str | Path = "weekly_plans", filename: str | None = None
) -> Path:
    """
    Save the given markdown string to a .md file inside `output_dir`.
    """
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    if filename is None:
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"week_plan_{ts}.md"

    path = target_dir / filename
    path.write_text(markdown.strip(), encoding="utf-8")
    return path


def append_memory_snippet(snippet: str, path: str | Path = "docs/memory.md") -> Path:
    """
    Append a short memory snippet to the given file.
    Creates the docs directory and file if they do not exist.
    Each entry is prefixed with a heading containing today's date.
    """
    memory_path = Path(path)
    memory_path.parent.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    entry = f"\n\n## Week starting {today}\n{snippet.strip()}\n"

    with memory_path.open("a", encoding="utf-8") as file:
        file.write(entry)

    return memory_path


def read_recent_memory(
    path: str | Path = "docs/memory.md", max_chars: int = 2000
) -> Optional[str]:
    """
    Read the memory file and return a recent snippet as a string.

    - If the file does not exist, return None.
    - If it exists, read its contents.
    - If the file is very long, return only the last `max_chars` characters
      (to keep the prompt size reasonable).
    """
    memory_path = Path(path)
    if not memory_path.exists():
        return None

    text = memory_path.read_text(encoding="utf-8")
    if len(text) <= max_chars:
        return text.strip() or None

    snippet = text[-max_chars:]
    return snippet.strip() or None


def split_markdown_into_plan_and_linkedin(full_markdown: str) -> Tuple[str, str]:
    """Split the full markdown into the complete plan and the LinkedIn post section."""
    linkedin_heading = re.search(
        r"(?im)^[ \t]*(?:#{1,6}[ \t]*)?(?:\d+\.[ \t]*)?(?:[^\w\s#]+[ \t]*)?LinkedIn Post (?:Template|Draft)[ \t]*$",
        full_markdown,
    )

    if linkedin_heading:
        index = linkedin_heading.start()
        linkedin_section = full_markdown[index:]
        files_heading = re.search(
            r"(?im)^[ \t]*(?:#{1,6}[ \t]*)?(?:[^\w\s#]+[ \t]*)?Files to Generate[ \t]*$",
            linkedin_section,
        )
        if files_heading:
            linkedin_section = linkedin_section[:files_heading.start()]
        return full_markdown[:index].rstrip(), linkedin_section.strip()

    fallback = "LinkedIn post section not found in plan."
    return full_markdown, fallback


def save_week_files(
    plan_markdown: str,
    linkedin_markdown: str,
    base_dir: Path | str = ".",
    learning_unit_md: str | None = None,
    learning_unit_slug_source: str | None = None,
) -> Tuple[Path, Path, Path | None]:
    """Persist the weekly plan, LinkedIn draft, and optional learning unit to dated markdown files."""
    root = Path(base_dir)
    plan_dir = root / "weekly_plans"
    posts_dir = root / "posts"
    plan_dir.mkdir(parents=True, exist_ok=True)
    posts_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
    plan_path = plan_dir / f"week_{ts}_plan.md"
    linkedin_path = posts_dir / f"linkedin_week_{ts}.md"

    plan_path.write_text(plan_markdown.strip(), encoding="utf-8")
    linkedin_path.write_text(linkedin_markdown.strip(), encoding="utf-8")

    learning_unit_path = None
    if learning_unit_md and learning_unit_md.strip():
        learning_unit_path = save_learning_unit(
            markdown=learning_unit_md,
            base_dir=root,
            timestamp=ts,
            slug_source=learning_unit_slug_source or learning_unit_md,
        )
        learning_unit_mtime = os.path.getmtime(learning_unit_path)
        print(f"Learning unit saved to {learning_unit_path} (mtime={learning_unit_mtime})")

    return plan_path, linkedin_path, learning_unit_path


def _extract_learning_unit_title(learning_unit_md: str) -> str | None:
    for line in learning_unit_md.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or None
    return None


def _slugify(text: str, max_len: int = 50) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if not slug:
        return "learning-unit"
    return slug[:max_len].strip("-") or "learning-unit"


def save_learning_unit(
    markdown: str,
    base_dir: Path | str,
    timestamp: str,
    slug_source: str,
) -> Path:
    """Save the learning unit markdown under docs/learning_units with a timestamped filename."""
    target_dir = Path(base_dir) / "docs" / "learning_units"
    target_dir.mkdir(parents=True, exist_ok=True)

    title = _extract_learning_unit_title(markdown) or slug_source
    slug = _slugify(title)
    path = target_dir / f"{timestamp}_{slug}.md"
    path.write_text(markdown.strip(), encoding="utf-8")
    return path


def save_day_learning_unit(
    markdown: str,
    base_dir: Path | str,
    day_id: str,
    slug_source: str,
) -> Path:
    """Save a learning unit for one day under docs/learning_units."""
    target_dir = Path(base_dir) / "docs" / "learning_units"
    target_dir.mkdir(parents=True, exist_ok=True)
    slug = _slugify(slug_source)
    path = target_dir / f"{day_id}_{slug}.md"
    path.write_text(markdown.strip(), encoding="utf-8")
    return path


def generate_weekly_plan_and_learning_unit(
    goal: str,
    time_per_week_hours: float,
    max_session_minutes: int,
    preferences: str | None,
    memory_context: str,
    memory_used: bool,
    memory_source: str,
    memory_char_count: int,
    task_progress: TaskProgressSummary | None = None,
    roadmap_context: str | None = None,
    roadmap_progress: str | None = None,
    week_number: int | None = None,
    target_level: str | None = None,
    background: str | None = None,
    model: str = DEFAULT_MODEL,
    learner_setup: dict | None = None,
) -> dict:
    """Generate the weekly plan and learning unit via separate LLM calls."""
    plan_system_prompt, plan_user_prompt = build_weekly_planner_prompt(
        goal=goal,
        time_per_week_hours=time_per_week_hours,
        max_session_minutes=max_session_minutes,
        preferences=preferences,
        memory_context=memory_context,
        memory_used=memory_used,
        memory_source=memory_source,
        memory_char_count=memory_char_count,
        task_progress=task_progress,
        roadmap_context=roadmap_context,
        roadmap_progress=roadmap_progress,
        week_number=week_number,
        target_level=target_level,
        background=background,
        learner_setup=learner_setup,
    )

    raw_plan_output = call_llm(
        system_prompt=plan_system_prompt,
        user_prompt=plan_user_prompt,
        model=model,
        max_tokens=PLAN_MAX_TOKENS,
    )
    memory_audit_block = raw_plan_output.split("<<PLAN_MARKDOWN>>", 1)[0].strip()
    plan_text = extract_between(raw_plan_output, "<<PLAN_MARKDOWN>>", "<<END_PLAN>>")
    memory_snippet = extract_between(raw_plan_output, "<<MEMORY_SNIPPET>>", "<<END_MEMORY>>")

    formatted_markdown = format_weekly_plan(plan_text)
    formatted_markdown = enforce_week_heading(formatted_markdown, week_number or 1)
    if memory_audit_block:
        formatted_markdown = f"{memory_audit_block}\n\n{formatted_markdown}"
    plan_markdown, linkedin_markdown = split_markdown_into_plan_and_linkedin(formatted_markdown)
    plan_markdown = remove_duplicate_daily_breakdown_sections(plan_markdown)

    if learner_setup is not None:
        days = parse_days_from_plan(plan_markdown)
        if not days or any(day["estimated_minutes"] <= 0 for day in days):
            raise ValueError("Weekly plan must include learning days with explicit durations.")
        if any(day["estimated_minutes"] > max_session_minutes for day in days):
            raise ValueError("Weekly plan exceeds the configured maximum session length.")
        if sum(day["estimated_minutes"] for day in days) > time_per_week_hours * 60:
            raise ValueError("Weekly plan exceeds the configured weekly time budget.")

    roadmap_tags = _extract_roadmap_tags(plan_markdown)
    plan_context = _truncate_text(plan_markdown, max_chars=1400)
    unit_system_prompt, unit_user_prompt = build_learning_unit_prompt(
        goal=goal,
        preferences=preferences,
        memory_context=_truncate_text(memory_context, max_chars=1000),
        roadmap_tags=roadmap_tags,
        roadmap_context=_truncate_text(roadmap_context or "", max_chars=1000) if roadmap_context else None,
        plan_context=render_prompt("learning_unit.plan_excerpt", plan_context=plan_context),
        target_level=target_level,
        background=background,
        learner_setup=learner_setup,
    )

    raw_learning_unit_output = call_llm(
        system_prompt=unit_system_prompt,
        user_prompt=unit_user_prompt,
        model=model,
        max_tokens=UNIT_MAX_TOKENS,
    )
    learning_unit_md = extract_learning_unit(raw_learning_unit_output)
    if not learning_unit_md:
        learning_unit_md = raw_learning_unit_output.strip()
    if not learning_unit_md:
        learning_unit_md = "# Learning Unit\n\nLearning unit generation failed."

    quality = check_learning_unit_quality(learning_unit_md)
    if not quality.get("ok"):
        print(f"Learning unit quality issues: {quality.get('issues')}")
        retry_prompt = render_prompt(
            "learning_unit.weekly_repair",
            unit_user_prompt=unit_user_prompt,
            issues=', '.join(quality.get('issues', [])),
            missing_definitions=', '.join(quality.get('missing_definitions', [])),
        )
        raw_retry_output = call_llm(
            system_prompt=unit_system_prompt,
            user_prompt=retry_prompt,
            model=model,
            max_tokens=UNIT_MAX_TOKENS,
        )
        learning_unit_md = extract_learning_unit(raw_retry_output) or raw_retry_output.strip()
        if not learning_unit_md:
            learning_unit_md = "# Learning Unit\n\nLearning unit generation failed."
        retry_quality = check_learning_unit_quality(learning_unit_md)
        if not retry_quality.get("ok"):
            print(f"Learning unit retry issues: {retry_quality.get('issues')}")

    return {
        "plan_markdown": plan_markdown,
        "linkedin_markdown": linkedin_markdown,
        "memory_snippet": memory_snippet,
        "learning_unit_md": learning_unit_md,
        "raw_plan_output": raw_plan_output,
        "raw_learning_unit_output": raw_learning_unit_output,
    }


def generate_and_save_week(
    goal: str,
    time_per_week_hours: float,
    max_session_minutes: int = 30,
    preferences: str | None = None,
    target_level: str | None = None,
    background: str | None = None,
    roadmap_id: str | None = None,
    force_regenerate_roadmap: bool = False,
    learner_setup: dict | None = None,
    model: str = DEFAULT_MODEL,
    base_dir: Path | str = ".",
) -> dict:
    """High-level orchestrator that builds prompts, calls the LLM, splits, and saves files."""
    from .learner_setup import make_learner_setup, validate_learner_setup
    learner_setup = validate_learner_setup(learner_setup) if learner_setup is not None else make_learner_setup(
        goal=goal, background=background or "", preferences=preferences or "",
        hours_per_week=time_per_week_hours, max_session_minutes=max_session_minutes,
        learning_intensity=target_level or "medium",
    )
    memory_path = Path(base_dir) / "docs" / "memory.md"
    memory_source = (Path(base_dir) / "data" / "memory_vectors.json").as_posix()

    store = LocalVectorStore(path=Path(base_dir) / "data" / "memory_vectors.json")

    query_text = f"{goal}\npreferences: {preferences or ''}"
    results = store.search(query_text, top_k=5)

    if results:
        # Use only relevant memories
        snippets = []
        for score, item in results:
            snippets.append(f"- (score={score:.3f}) {item.text.strip()}")
        memory_context = (
            "Top relevant notes from past weeks (semantic search):\n"
            + "\n".join(snippets)
            + "\n"
        )
        memory_used = True
        memory_char_count = len(memory_context)
    else:
        # Fallback: first-week behavior
        memory_context = render_prompt("weekly_plan.no_memory")
        memory_used = False
        memory_char_count = 0

    tasks_path = Path(base_dir) / "data" / "tasks.csv"
    task_progress = summarize_task_progress(tasks_path)

    roadmap_context = None
    roadmap_progress = None
    week_number = None
    roadmap_meta = {}
    roadmap_path = ""
    roadmap = None
    effective_roadmap_id = ""
    from . import tools as tools_module

    if force_regenerate_roadmap:
        roadmap_result = tools_module.tool_generate_learning_roadmap(
            goal=goal,
            target_level=target_level or "medium",
            background=background,
            roadmap_id=roadmap_id,
            base_dir=Path(base_dir),
            model=model,
            learner_setup=learner_setup,
        )
        if roadmap_result.get("error"):
            raise ValueError(roadmap_result["error"])
        roadmap = roadmap_result.get("roadmap")
        roadmap_path = roadmap_result.get("path", "")
        effective_roadmap_id = roadmap_result.get("roadmap_id") or ""
    else:
        load_result = tools_module.tool_load_learning_roadmap(
            goal=goal,
            base_dir=Path(base_dir),
            roadmap_id=roadmap_id,
            learning_purpose=learner_setup["learning_purpose"],
            force_regenerate=False,
        )
        if load_result.get("error"):
            raise ValueError(load_result["error"])
        roadmap = load_result.get("roadmap")
        roadmap_path = load_result.get("path", "")
        if not roadmap:
            roadmap_result = tools_module.tool_generate_learning_roadmap(
                goal=goal,
                target_level=target_level or "medium",
                background=background,
                roadmap_id=roadmap_id,
                base_dir=Path(base_dir),
                model=model,
                learner_setup=learner_setup,
            )
            if roadmap_result.get("error"):
                raise ValueError(roadmap_result["error"])
            roadmap = roadmap_result.get("roadmap")
            roadmap_path = roadmap_result.get("path", "")
            effective_roadmap_id = roadmap_result.get("roadmap_id") or ""

    if roadmap:
        learner_setup = validate_learner_setup(roadmap.get("learner_setup"))
        effective_roadmap_id = effective_roadmap_id or tools_module._infer_roadmap_id(goal, roadmap_id, roadmap_path)
        progress = tools_module._compute_roadmap_progress(
            roadmap, load_tasks(tasks_path), time_per_week_hours, effective_roadmap_id
        )
        roadmap_context = tools_module._format_roadmap_context(roadmap, progress)
        roadmap_progress = tools_module._format_roadmap_progress(roadmap, progress)
        week_number = progress.get("week_number")
        roadmap_meta = {
            "roadmap_path": roadmap_path or "",
            "roadmap_id": effective_roadmap_id,
            "total_estimated_hours": roadmap.get("total_estimated_hours"),
            "estimated_weeks_at_hours_per_week": roadmap.get("estimated_weeks_at_hours_per_week"),
            "phase_count": len(roadmap.get("phases", [])),
            "current_phase": progress.get("current_phase_id"),
            "current_milestone": progress.get("current_milestone_id"),
            "remaining_hours": progress.get("remaining_hours"),
            "week_number": progress.get("week_number"),
            "completed_hours": progress.get("completed_hours"),
            "completed_milestones": progress.get("completed_milestones"),
            "computed_week_number": progress.get("computed_week_number"),
            "milestone_task_counts": progress.get("milestone_task_counts"),
            "milestone_completion_mode": progress.get("milestone_completion_mode"),
            "used_hours_per_week": progress.get("used_hours_per_week"),
            "debug_notes": progress.get("debug_notes"),
        }

    generation = generate_weekly_plan_and_learning_unit(
        goal=goal,
        time_per_week_hours=time_per_week_hours,
        max_session_minutes=max_session_minutes,
        preferences=preferences,
        memory_context=memory_context,
        memory_used=memory_used,
        memory_source=memory_source,
        memory_char_count=memory_char_count,
        task_progress=task_progress,
        roadmap_context=roadmap_context,
        roadmap_progress=roadmap_progress,
        week_number=week_number,
        target_level=target_level,
        background=background,
        model=model,
        learner_setup=learner_setup,
    )
    plan_markdown = generation["plan_markdown"]
    linkedin_markdown = generation["linkedin_markdown"]
    memory_snippet = generation["memory_snippet"]
    learning_unit_md = generation["learning_unit_md"]

    upsert_tasks_from_plan(
        plan_md=plan_markdown,
        tasks_path=tasks_path,
        source_week=date.today().isoformat(),
        default_priority=3,
    )

    plan_path, linkedin_path, learning_unit_path = save_week_files(
        plan_markdown=plan_markdown,
        linkedin_markdown=linkedin_markdown,
        base_dir=base_dir,
        learning_unit_md=learning_unit_md,
        learning_unit_slug_source=goal,
    )
    learning_progress_path = resolve_learning_progress_path(Path(base_dir))
    _progress, progress_week = append_week_from_plan(
        path=learning_progress_path,
        plan_md=plan_markdown,
        roadmap_id=roadmap_meta.get("roadmap_id", "") or "",
        phase_id=roadmap_meta.get("current_phase", "") or "",
        milestone_id=roadmap_meta.get("current_milestone", "") or "",
        week_number_global=roadmap_meta.get("week_number"),
        goal=goal,
        plan_path=plan_path.relative_to(Path(base_dir)).as_posix(),
        learning_unit_path=learning_unit_path.relative_to(Path(base_dir)).as_posix() if learning_unit_path else "",
    )

    if memory_snippet:
        memory_path = append_memory_snippet(memory_snippet, path=memory_path)
        store.add(
            text=memory_snippet.strip(),
            meta={"date": date.today().isoformat(), "goal": goal},
        )
        print(f"Weekly plan saved to {plan_path}")
        print(f"Memory updated at {memory_path}")
    else:
        print(f"Weekly plan saved to {plan_path} (no memory snippet found)")

    return {
        "plan_path": plan_path,
        "linkedin_path": linkedin_path,
        "raw_markdown": generation.get("raw_plan_output", ""),
        "memory_path": memory_path,
        "learning_unit_path": learning_unit_path,
        "learning_progress_path": learning_progress_path,
        "learning_progress_week_id": progress_week.get("week_id", ""),
        "roadmap_path": roadmap_meta.get("roadmap_path", ""),
        "roadmap_total_hours": roadmap_meta.get("total_estimated_hours"),
        "roadmap_estimated_weeks": roadmap_meta.get("estimated_weeks_at_hours_per_week"),
        "roadmap_phase_count": roadmap_meta.get("phase_count"),
        "roadmap_current_phase": roadmap_meta.get("current_phase"),
        "roadmap_current_milestone": roadmap_meta.get("current_milestone"),
        "roadmap_remaining_hours": roadmap_meta.get("remaining_hours"),
        "roadmap_week_number": roadmap_meta.get("week_number"),
        "roadmap_completed_hours": roadmap_meta.get("completed_hours"),
        "roadmap_completed_milestones": roadmap_meta.get("completed_milestones"),
        "roadmap_computed_week_number": roadmap_meta.get("computed_week_number"),
        "roadmap_milestone_task_counts": roadmap_meta.get("milestone_task_counts"),
        "roadmap_completion_mode": roadmap_meta.get("milestone_completion_mode"),
        "roadmap_used_hours_per_week": roadmap_meta.get("used_hours_per_week"),
        "roadmap_debug_notes": roadmap_meta.get("debug_notes"),
    }


def format_summary(plan_path: Path, linkedin_path: Path) -> str:
    """Return a short summary string of generated artifacts."""
    return (
        f"Weekly plan saved to: {plan_path.resolve()}\n"
        f"LinkedIn draft saved to: {linkedin_path.resolve()}"
    )


if __name__ == "__main__":
    example_goal = "continue agent workflow + embeddings"
    try:
        result = generate_and_save_week(
            goal=example_goal,
            time_per_week_hours=2.0,
            max_session_minutes=30,
            preferences="visual learning, portfolio focus",
        )
        print(f"Weekly plan generated and saved to {result['plan_path']}")
    except Exception as exc:  # pragma: no cover - runtime demo
        print(f"Error generating weekly plan: {exc}")
