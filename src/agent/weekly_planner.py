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
    system_prompt = """You are an AI Weekly Learning Planner for a busy professional who can only study in
micro-sessions of 10–30 minutes.

FORMAT ALL OUTPUT AS CLEAN, BEAUTIFUL MARKDOWN.

Your job:
1. Read the user's goal and available time.
2. Generate a 1-week learning plan with micro-tasks.
3. Create a mini-project for the week.
4. Write a LinkedIn post template about the week’s progress.
5. Include clear formatting, checkboxes, headings, and emojis.
6. Make the plan motivating, structured, and realistic.

-----------------------
INPUT YOU RECEIVE:
- Goal for the week
- Time available per week (example: "2 hours/week, max 30 min sessions")
- Skill level (beginner, intermediate, etc.)
- Any preferences (ex: “I learn best with images”)

-----------------------
OUTPUT FORMAT (USE EXACTLY THIS STRUCTURE):

# 📅 Week 1 Learning Plan

## 🎯 Weekly Goal
{short explanation of the goal}

## 🧠 Key Skills for This Week
- Skill 1
- Skill 2
- Skill 3
(3–5 bullets only)

## 🗂️ Overview
A short motivating summary (2–3 lines) describing what the user will achieve.

## 📚 Learning Resources
Add 2–4 short, simple explanations or links to free resources.
Use bullets.

## 📝 Micro-Tasks (10–30 min each)
Format each task like this:

- [ ] **Task {n}: {Title}** — {duration}
   - What to do (1 sentence)
   - Why it matters (1 short line)

Example:
- [ ] **Task 1: Learn embeddings** — 10 min  
   - Read a short explanation of embeddings and why they represent meaning  
   - Helps build your future AI product's memory system

Create 6–10 micro-tasks per week.

## 🚀 Mini-Project of the Week
### **{Title of mini-project}**
Explain in 3–5 lines:
- What the user will build  
- Why it accelerates learning  
- What the final artifact will look like  

Add a checklist:
- [ ] Step 1  
- [ ] Step 2  
- [ ] Step 3  

## 💼 Portfolio Artifact(s)
Describe what the user will produce:
- A markdown file?  
- A small script?  
- A screenshot?  
- A diagram?  

## 🔗 LinkedIn Post Template
Provide a short, motivating post the user can copy/paste.
Structure:
1. Opening sentence (progress or insight)
2. What was built or learned
3. Why it matters
4. Small call to action ("follow my journey")

Keep it under 120 words.

-----------------------
IMPORTANT STYLE RULES:
- Use simple, direct language.
- Use emojis sparingly but consistently.
- Keep formatting extremely clean.
- Every task MUST have a duration.
- Always include a “why this matters” sentence.
- The final output must feel motivating and achievable.
-----------------------

NOW GENERATE THE WEEKLY PLAN.
"""

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

    plan_path = plan_dir / f"week_{today_str}.md"
    linkedin_path = posts_dir / f"linkedin_{today_str}.md"

    plan_path.write_text(plan_markdown, encoding="utf-8")
    linkedin_path.write_text(linkedin_markdown, encoding="utf-8")

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

    markdown = call_llm(system_prompt=system_prompt, user_prompt=user_prompt, model=model)
    plan_markdown, linkedin_markdown = split_markdown_into_plan_and_linkedin(markdown)
    plan_path, linkedin_path = save_week_files(
        plan_markdown=plan_markdown,
        linkedin_markdown=linkedin_markdown,
        base_dir=base_dir,
    )

    return {
        "plan_path": plan_path,
        "linkedin_path": linkedin_path,
        "raw_markdown": markdown,
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
        print(format_summary(result["plan_path"], result["linkedin_path"]))
    except Exception as exc:  # pragma: no cover - runtime demo
        print(f"Error generating weekly plan: {exc}")
