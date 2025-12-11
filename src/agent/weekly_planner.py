"""Weekly planner agent utilities for generating learning plans via OpenAI."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Tuple

from openai import OpenAI

DEFAULT_MODEL = os.getenv("PLANNER_MODEL", "gpt-4o-mini")
MAX_TOKENS = int(os.getenv("PLANNER_MAX_TOKENS", "1800"))


def build_weekly_planner_prompt(
    goal: str,
    time_per_week_hours: float,
    max_session_minutes: int,
    preferences: str | None,
) -> Tuple[str, str]:
    """Construct system and user prompts for the weekly planner agent."""
    system_prompt = """You are an AI Weekly Learning Planner. Generate a clean, motivating weekly plan that fits into 10–30 minute sessions. Return only raw Markdown (no code fences).

OUTPUT TEMPLATE (FOLLOW EXACTLY):

Week X Learning Plan
📌 Summary of Goals
- One-sentence summary of the week
- 2–3 key focus areas

🗓️ Daily Breakdown
Day 1: <short theme>
- <subtask 1>
- <subtask 2>

Day 2: <short theme>
- <subtask 1>
- <subtask 2>

Day 3: <short theme>
- <subtask 1>
- <subtask 2>

Day 4: <short theme>
- <subtask 1>
- <subtask 2>

Day 5: <short theme>
- <subtask 1>
- <subtask 2>

🧩 Micro Tasks (10–30 min)
⭐ Task 1 (10 min): <description>
⭐ Task 2 (15 min): <description>
⭐ Task 3 (30 min): <description>

🧪 Mini Project for the Week
Title: <short title>
Scope:
- <bullet 1>
- <bullet 2>
- <bullet 3>

💬 LinkedIn Post Template
<one paragraph the user can adapt and post on LinkedIn>

📂 Files to Generate
- /weekly_plans/week_X_plan.md
- /posts/linkedin_week_X.md
- /tasks/task_X.md

STYLE RULES:
- Use headings, bullets, and checkboxes exactly as shown.
- Keep language concise and encouraging.
- No code fences. Output only the Markdown content."""

    user_prompt = f"""Goal for the week: {goal}
Time available per week: {time_per_week_hours} hours
Max session length: {max_session_minutes} minutes
Skill level: intermediate data scientist
Preferences: {preferences or 'none'}

The user is a working parent with limited energy. Suggest a realistic plan that fits into 10–30 minute focused blocks."""

    return system_prompt, user_prompt


def call_llm(system_prompt: str, user_prompt: str, model: str = DEFAULT_MODEL) -> str:
    """Call OpenAI's chat completions API and return the assistant markdown string."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set.")

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=MAX_TOKENS,
            temperature=0.5,
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
                f"[WeeklyPlanner] Token usage — prompt: {usage.prompt_tokens}, "
                f"completion: {usage.completion_tokens}, total: {usage.total_tokens}"
            )
        except Exception:
            pass

    return message


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


def save_weekly_plan(
    markdown: str, output_dir: str | Path = "weekly_plans", filename: str | None = None
) -> Path:
    """
    Save the given markdown string to a .md file inside `output_dir`.
    """
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    if filename is None:
        filename = f"week_plan_{date.today().isoformat()}.md"

    path = target_dir / filename
    path.write_text(markdown.strip(), encoding="utf-8")
    return path


def split_markdown_into_plan_and_linkedin(full_markdown: str) -> Tuple[str, str]:
    """Split the full markdown into the complete plan and the LinkedIn post section."""
    new_heading = "## 🔗 LinkedIn Post Template"
    old_heading = "## 5. LinkedIn Post Draft"

    index = full_markdown.find(new_heading)
    if index == -1:
        index = full_markdown.find(old_heading)

    if index != -1:
        return full_markdown, full_markdown[index:]

    fallback = "LinkedIn post section not found in plan."
    return full_markdown, fallback


def save_week_files(
    plan_markdown: str, linkedin_markdown: str, base_dir: Path | str = "."
) -> Tuple[Path, Path]:
    """Persist the weekly plan and LinkedIn draft to dated markdown files."""
    root = Path(base_dir)
    today_str = date.today().isoformat()

    plan_dir = root / "weekly_plans"
    posts_dir = root / "posts"
    plan_dir.mkdir(parents=True, exist_ok=True)
    posts_dir.mkdir(parents=True, exist_ok=True)

    plan_path = plan_dir / f"week_{today_str}_plan.md"
    linkedin_path = posts_dir / f"linkedin_week_{today_str}.md"

    plan_path.write_text(plan_markdown.strip(), encoding="utf-8")
    linkedin_path.write_text(linkedin_markdown.strip(), encoding="utf-8")

    return plan_path, linkedin_path


def generate_and_save_week(
    goal: str,
    time_per_week_hours: float,
    max_session_minutes: int = 30,
    preferences: str | None = None,
    model: str = DEFAULT_MODEL,
    base_dir: Path | str = ".",
) -> dict:
    """High-level orchestrator that builds prompts, calls the LLM, splits, and saves files."""
    system_prompt, user_prompt = build_weekly_planner_prompt(
        goal=goal,
        time_per_week_hours=time_per_week_hours,
        max_session_minutes=max_session_minutes,
        preferences=preferences,
    )

    raw_markdown = call_llm(system_prompt=system_prompt, user_prompt=user_prompt, model=model)
    formatted_markdown = format_weekly_plan(raw_markdown)
    plan_markdown, linkedin_markdown = split_markdown_into_plan_and_linkedin(formatted_markdown)

    plan_path = save_weekly_plan(
        markdown=plan_markdown,
        output_dir=Path(base_dir) / "weekly_plans",
    )

    posts_dir = Path(base_dir) / "posts"
    posts_dir.mkdir(parents=True, exist_ok=True)
    linkedin_path = posts_dir / f"linkedin_week_{date.today().isoformat()}.md"
    linkedin_path.write_text(linkedin_markdown.strip(), encoding="utf-8")

    return {
        "plan_path": plan_path,
        "linkedin_path": linkedin_path,
        "raw_markdown": raw_markdown,
    }


def format_summary(plan_path: Path, linkedin_path: Path) -> str:
    """Return a short summary string of generated artifacts."""
    return (
        f"Weekly plan saved to: {plan_path.resolve()}\n"
        f"LinkedIn draft saved to: {linkedin_path.resolve()}"
    )


if __name__ == "__main__":
    example_goal = "Modern AI foundations + build my first agent"
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
