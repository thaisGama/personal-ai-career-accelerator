"""Weekly planner agent utilities for generating learning plans via OpenAI."""

from __future__ import annotations

import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Tuple

from openai import OpenAI

from .memory.vector_store import LocalVectorStore
from .task_store import TaskProgressSummary, summarize_task_progress, upsert_tasks_from_plan

DEFAULT_MODEL = os.getenv("PLANNER_MODEL", "gpt-4o-mini")
MAX_TOKENS = int(os.getenv("PLANNER_MAX_TOKENS", "1800"))


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
    target_level: str | None = None,
    background: str | None = None,
) -> Tuple[str, str]:
    """Construct system and user prompts for the weekly planner agent."""
    system_prompt = """You are an AI Weekly Learning Planner. Generate a clean, motivating weekly plan that fits into 10–30 minute sessions. Return only raw Markdown (no code fences).

You must BEGIN your output with EXACTLY the following MEMORY_AUDIT block (no text before it). Do not change the provided values. For the Memory focus line, write one short sentence about what from memory influenced this plan, or "None" if nothing applied:

MEMORY_AUDIT (must be echoed exactly at the very top of the output):
Memory used: {MEMORY_USED}
Memory source: {MEMORY_SOURCE}
Memory characters injected: {MEMORY_CHAR_COUNT}
Memory focus: <1 short sentence about what from memory influenced this plan, or "None">

At the end of your response, add a short “memory snippet” describing the week’s focus and the key intentions in 2–4 bullet points.

After the plan block and before the memory snippet, include a <<LEARNING_UNIT>> block with study-ready teaching content. It must be self-contained and include:
- Decision lens (use when / don't use when)
- Mental model
- "How It Works (No Math)" section
- 2–3 worked examples (problem → why naive fails → why this tool fits → system sketch)
- Mini-project blueprint (pipeline, what to tune, debugging checklist, definition of done)
- Optional deepening resources: max 2, free, title + platform + search phrase (no URLs)

Learning unit resource rules:
- At most 2 resources and they must be FREE.
- Each resource must be uniquely identifiable: specific title + owner/publisher + platform + a search phrase that reliably surfaces it.
- Avoid generic titles like "Beginner's guide to ..." or "Introduction to ..." unless paired with a unique owner/publisher and platform.
- Format resources as: Title — Owner — Platform — search phrase: "..."

Learning unit depth and length rules:
- Target length: 600–1200 words total.
- Intro/foundations exception: 400–700 words if the roadmap milestone explicitly signals intro/foundations.
- Worked Examples must include 2–3 examples.
- Mini-Project Blueprint must include: input format, pipeline steps, what to tune, debugging checklist, definition of done.
- If length is short, expand Worked Examples and Mini-Project Blueprint rather than adding history.

Use this exact output format (do not include explanations):

<<PLAN_MARKDOWN>>
Week X Learning Plan
📌 Summary of Goals
- One-sentence summary of the week
- 2–3 key focus areas

🗓️ Daily Breakdown
In the "🗓️ Daily Breakdown" section, list only the main focus/theme for each day (no detailed tasks). Example:
- Day 1: AI foundations and terminology
- Day 2: Supervised vs. unsupervised learning
- Day 3: First agent concept, etc.

🗓️ Daily Breakdown
Day 1: <short theme>
Day 2: <short theme>
Day 3: <short theme>
Day 4: <short theme>
Day 5: <short theme>

In the section "🧩 Micro Tasks (10–30 min)", generate 3–5 very concrete micro-tasks.

Each micro-task MUST include:

- A title + duration + priority emoji (🔥 high, ⭐ medium, 🌱 low)
- A Learning capsule (a short, self-contained explanation of the core idea, length depends on Learning intensity)
- A Key takeaways list (3–5 bullets of what the user should know after this task)
- A Suggested resource (optional) – at most ONE resource:
  - Prefer either:
    - a well-known canonical source by name (official docs, papers, blogs), OR
    - a focused description + search phrase for a named reference.
  - Do NOT invent precise URLs. Use titles + platforms + search phrases instead.
  - Avoid "search YouTube" as a primary method; videos are OK only when a named canonical source is suggested.
- A tiny Output (what the user will produce), like updating a notes file or running a small example.

Use this exact markdown structure for each micro-task:

- 🔥 **Task 1 (20 min): Short title here**  
  - **Learning capsule (length by intensity):**  
    Short, focused explanation of the core idea for this task that the user can read without leaving the file.
  - **Key takeaways:**  
    - bullet 1  
    - bullet 2  
    - bullet 3
  - **Suggested resource (optional):**  
    Short description and, if appropriate, a title + platform + search phrase.
  - **Output:**  
    Very small, concrete result (e.g. "add 5 bullet notes to notes/ai_foundations.md" or "run the example script and write 3 lines about what happened").

Make the learning capsule and key takeaways accurate and compact. The user should be able to learn the essentials just by reading the plan, even if they don't open the external resource.

LEARNING MATERIAL POLICY

When producing learning content (learning capsule, explanations, or task instructions):

1) The core explanation MUST be generated by you.
   - Assume the learner has no external resources.
   - Explain concepts clearly, using intuition and simple mental models.
   - Prefer concrete examples over abstract theory.

2) Each learning unit must include at least:
   - one intuitive explanation
   - one concrete example (code, pseudo-code, or scenario)
   - one short exercise or reflection task the learner can do immediately

3) External resources are OPTIONAL and secondary.
   - Prefer freely available resources only (official docs, reputable blogs, open GitHub repos).
   - Never require a resource to complete a task.
   - Limit to at most 1–2 external links per week or milestone.
   - If mentioned, label them explicitly as OPTIONAL.

4) Paid resources (books, courses, subscriptions):
   - Must NEVER be required.
   - May be mentioned only as OPTIONAL enrichment.
   - Must be clearly labeled as OPTIONAL (do not imply necessity).

The generated plan should be fully usable without clicking any external link.

🧪 Mini Project for the Week
Title: <short title>
Scope:
- <bullet 1>
- <bullet 2>
- <bullet 3>

✅ Next Actions
- <action 1>
- <action 2>
- <action 3>

💬 LinkedIn Post Template
<one paragraph the user can adapt and post on LinkedIn>

📂 Files to Generate
- /weekly_plans/week_X_plan.md
- /posts/linkedin_week_X.md
- /tasks/task_X.md
<<END_PLAN>>
<<LEARNING_UNIT>>
# <Title of the learning unit>

## Decision Lens (use when / don't use when)
- Use when:
- Don't use when:

## Mental Model
- <short mental model explanation>

## How It Works (No Math)
- <intuitive explanation>

## Worked Examples
- Example 1: <problem> → <why naive fails> → <why this tool fits> → <system sketch>
- Example 2: <problem> → <why naive fails> → <why this tool fits> → <system sketch>
- Example 3 (optional): <problem> → <why naive fails> → <why this tool fits> → <system sketch>

## Mini-Project Blueprint
- Input format:
- Pipeline steps:
- What to tune:
- Debugging checklist:
- Definition of done (DoD):

## Deepening Resources (Optional)
- <Title> — <Owner> — <Platform> — search phrase: "<phrase>"
- <Title> — <Owner> — <Platform> — search phrase: "<phrase>"
<<END_LEARNING_UNIT>>
<<MEMORY_SNIPPET>>
- bullet 1
- bullet 2
- bullet 3
<<END_MEMORY>>

For every micro-task in the "🧩 Micro Tasks" section, assign one priority tag:
- 🔥 High priority (critical for the week's goal)
- ⭐ Medium priority (helpful but not essential)
- 🌱 Low priority (optional stretch task)

Follow the micro-task structure shown above (include priority emoji, resource, what you'll learn bullets, and output).
If ROADMAP PROGRESS is provided, add a short "🧭 Roadmap Context" block right after the Week title with:
- Roadmap: topic | Target level
- Total estimate + typical duration at 2h/week
- Current focus: Phase P?, Milestone M?
- Week number (approx)
- Remaining hours (rough estimate)
If ROADMAP CONTEXT is provided, align micro-tasks to the current milestone and append tags to each micro-task title:
[phase:P#][milestone:M#.#]
Learning capsule length guidance by intensity:
- light: ~100–150 words
- medium: ~200–300 words
- hardcore: ~300–600 words

STYLE RULES:
- Use headings, bullets, and checkboxes exactly as shown.
- Keep language concise and encouraging.
- No code fences. Output only the Markdown content."""

    system_prompt = system_prompt.format(
        MEMORY_USED="YES" if memory_used else "NO",
        MEMORY_SOURCE=memory_source,
        MEMORY_CHAR_COUNT=memory_char_count,
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
        task_block = (
            "\n=== TASK PROGRESS (tasks.csv) ===\n"
            "Open tasks (top 5):\n"
            + ("\n".join(open_lines) if open_lines else "None")
            + "\nWeak topics:\n"
            + weak_topics
            + "\nTasks completed last week:\n"
            + completed
            + "\n=== END TASK PROGRESS ===\n"
        )

    roadmap_block = ""
    if roadmap_progress:
        roadmap_block += f"\n{roadmap_progress}\n"
    if roadmap_context:
        roadmap_block += f"\n{roadmap_context}\n"

    user_prompt = f"""Goal for the week: {goal}
Time available per week: {time_per_week_hours} hours
Max session length: {max_session_minutes} minutes
Skill level: intermediate data scientist
Learning intensity: {target_level or 'medium'}
Background / constraints: {background or 'none'}
Preferences: {preferences or 'none'}

You are planning a new learning week for the user. You are given some memory from previous weeks (what they did, planned, or learned). Use it to:
- avoid repeating identical tasks unless repetition is explicitly useful for mastery
- connect this week’s tasks to what they did before ("last week you started X, this week you'll continue with Y")
- adjust difficulty and scope logically, and if the user struggled with something, include a brief review task rather than repeating the full effort.

=== CONTEXT FROM PAST WEEKS ===
{memory_context}
=== END CONTEXT ===
{task_block}
{roadmap_block}

Use tasks.csv to avoid repeating tasks already marked DONE. Prefer NEEDS_REVIEW or IN_PROGRESS tasks when picking new work.

The user is a working parent with limited energy. Suggest a realistic plan that fits into 10–30 minute focused blocks."""

    return system_prompt, user_prompt


def call_llm(
    system_prompt: str,
    user_prompt: str,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.5,
) -> str:
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
            temperature=temperature,
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
    new_heading = "## 🔗 LinkedIn Post Template"
    old_heading = "## 5. LinkedIn Post Draft"

    index = full_markdown.find(new_heading)
    if index == -1:
        index = full_markdown.find(old_heading)

    if index != -1:
        return full_markdown[:index].rstrip(), full_markdown[index:].lstrip()

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

    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
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


def generate_and_save_week(
    goal: str,
    time_per_week_hours: float,
    max_session_minutes: int = 30,
    preferences: str | None = None,
    model: str = DEFAULT_MODEL,
    base_dir: Path | str = ".",
) -> dict:
    """High-level orchestrator that builds prompts, calls the LLM, splits, and saves files."""
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
        memory_context = "There is no relevant past memory yet. Plan as if this is the first week.\n"
        memory_used = False
        memory_char_count = 0

    tasks_path = Path(base_dir) / "data" / "tasks.csv"
    task_progress = summarize_task_progress(tasks_path)

    system_prompt, user_prompt = build_weekly_planner_prompt(
        goal=goal,
        time_per_week_hours=time_per_week_hours,
        max_session_minutes=max_session_minutes,
        preferences=preferences,
        memory_context=memory_context,
        memory_used=memory_used,
        memory_source=memory_source,
        memory_char_count=memory_char_count,
        task_progress=task_progress,
    )

    raw_markdown = call_llm(system_prompt=system_prompt, user_prompt=user_prompt, model=model)
    memory_audit_block = raw_markdown.split("<<PLAN_MARKDOWN>>", 1)[0].strip()
    plan_text = extract_between(raw_markdown, "<<PLAN_MARKDOWN>>", "<<END_PLAN>>")
    learning_unit_md = extract_learning_unit(raw_markdown)
    memory_snippet = extract_between(raw_markdown, "<<MEMORY_SNIPPET>>", "<<END_MEMORY>>")

    formatted_markdown = format_weekly_plan(plan_text)
    if memory_audit_block:
        formatted_markdown = f"{memory_audit_block}\n\n{formatted_markdown}"
    plan_markdown, linkedin_markdown = split_markdown_into_plan_and_linkedin(formatted_markdown)

    upsert_tasks_from_plan(
        plan_md=plan_markdown,
        tasks_path=tasks_path,
        source_week=date.today().isoformat(),
        default_priority=3,
    )

    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    plan_path = save_weekly_plan(
        markdown=plan_markdown,
        output_dir=Path(base_dir) / "weekly_plans",
        filename=f"week_plan_{ts}.md",
    )

    posts_dir = Path(base_dir) / "posts"
    posts_dir.mkdir(parents=True, exist_ok=True)
    linkedin_path = posts_dir / f"linkedin_week_{date.today().isoformat()}.md"
    linkedin_path.write_text(linkedin_markdown.strip(), encoding="utf-8")

    learning_unit_path = None
    if learning_unit_md:
        learning_unit_path = save_learning_unit(
            markdown=learning_unit_md,
            base_dir=Path(base_dir),
            timestamp=ts,
            slug_source=goal,
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
        "raw_markdown": raw_markdown,
        "memory_path": memory_path,
        "learning_unit_path": learning_unit_path,
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
