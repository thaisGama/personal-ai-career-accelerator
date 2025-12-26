"""Lightweight learning check (micro-quiz) helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, Optional

from .weekly_planner import DEFAULT_MODEL, call_llm, extract_between

QUIZ_GENERATION_SYSTEM_PROMPT = """You are a concise learning coach. Generate a 5–7 minute micro-quiz (5 questions) for the given topic.
Return ONLY the quiz content using the exact tag structure below so it can be parsed reliably.

Required format (no extra text):
<<QUIZ>>
<friendly title for the quiz>

Questions (mix of short answer + 1–2 multiple choice):
- Q1) ...
- Q2) ...
- Q3) ...
- Q4) ...
- Q5) ...
<<ANSWER_KEY>>
- Q1: <succinct correct answer or bullet hints>
- Q2: ...
- Q3: ...
- Q4: ...
- Q5: ...
<<RUBRIC>>
- What "excellent" looks like: <1–2 bullets>
- What "acceptable" looks like: <1–2 bullets>
- What "needs work" looks like: <1–2 bullets>
<<FOLLOW_UP>>
- If score <= 6/10: <brief practice activity>
- If score > 6/10: <slightly harder follow-up task>
"""

QUIZ_EVALUATION_SYSTEM_PROMPT = """You are a strict yet supportive grader. Compare the provided quiz answer key with the learner's answers.
Return ONLY the evaluation block using the exact format below:

<<EVAL>>
- Score: X/10
- Mastery: LOW|DEVELOPING|SOLID
- Strong areas: <short description>
- Weak areas: <short description>
- Next practice (10–15 min): <one concrete practice task>
- Move-on decision: MOVE_ON|REPEAT
<<END_EVAL>>

Rules:
- Score 0–10 with partial credit.
- Map mastery: 0–4 -> LOW, 5–7 -> DEVELOPING, 8–10 -> SOLID.
- MOVE_ON only if SOLID and strong alignment with answer key; otherwise REPEAT with a focused practice suggestion."""


def slugify(text: str) -> str:
    """Convert a topic string into a filesystem-friendly slug."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug or "quiz"


def save_quiz_markdown(topic: str, quiz_markdown: str, base_dir: Path | str = ".") -> Path:
    """Persist quiz markdown to docs/quizzes with a dated filename."""
    root = Path(base_dir)
    quizzes_dir = root / "docs" / "quizzes"
    quizzes_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{date.today().isoformat()}_{slugify(topic)}.md"
    path = quizzes_dir / filename
    path.write_text(quiz_markdown.strip(), encoding="utf-8")
    return path


def generate_micro_quiz(
    topic: str,
    context_text: Optional[str] = None,
    model: str = DEFAULT_MODEL,
    base_dir: Path | str = ".",
) -> Dict[str, object]:
    """
    Create a 5-question micro-quiz for the topic and save it.
    """
    user_prompt = (
        f"Topic: {topic.strip()}\n"
        f"Context/notes (may be empty):\n{context_text.strip() if context_text else 'None provided.'}\n"
        "Generate the quiz now."
    )
    quiz_markdown = call_llm(QUIZ_GENERATION_SYSTEM_PROMPT, user_prompt, model=model)
    quiz_markdown = quiz_markdown.strip()

    quiz_path = save_quiz_markdown(topic=topic, quiz_markdown=quiz_markdown, base_dir=base_dir)
    return {"quiz_markdown": quiz_markdown, "quiz_path": quiz_path}


@dataclass
class QuizEvaluation:
    raw_evaluation: str
    eval_block: str
    score: Optional[float]
    mastery: Optional[str]
    move_on_decision: Optional[str]


def _parse_eval_block(eval_block: str) -> QuizEvaluation:
    score_match = re.search(r"Score:\s*([0-9]+(?:\.[0-9]+)?)\s*/\s*10", eval_block, flags=re.IGNORECASE)
    mastery_match = re.search(r"Mastery:\s*([A-Z]+)", eval_block, flags=re.IGNORECASE)
    move_on_match = re.search(r"Move-on decision:\s*([A-Z_]+)", eval_block, flags=re.IGNORECASE)

    score = float(score_match.group(1)) if score_match else None
    mastery = mastery_match.group(1).upper() if mastery_match else None
    move_on = move_on_match.group(1).upper() if move_on_match else None

    return QuizEvaluation(
        raw_evaluation=eval_block,
        eval_block=eval_block,
        score=score,
        mastery=mastery,
        move_on_decision=move_on,
    )


def evaluate_micro_quiz(
    topic: str,
    quiz_markdown: str,
    learner_answers: str,
    model: str = DEFAULT_MODEL,
) -> Dict[str, object]:
    """
    Evaluate learner answers against the quiz answer key.
    """
    user_prompt = (
        f"Topic: {topic.strip()}\n"
        "Here is the quiz (with answer key and rubric):\n"
        f"{quiz_markdown}\n\n"
        "Learner answers:\n"
        f"{learner_answers.strip() if learner_answers else 'No answers provided.'}\n"
        "Return ONLY the evaluation block."
    )
    raw_eval = call_llm(QUIZ_EVALUATION_SYSTEM_PROMPT, user_prompt, model=model)
    eval_block = extract_between(raw_eval, "<<EVAL>>", "<<END_EVAL>>")
    eval_block = eval_block if eval_block.strip() else raw_eval.strip()

    parsed = _parse_eval_block(eval_block)
    return {
        "raw_evaluation": raw_eval,
        "eval_block": eval_block,
        "score": parsed.score,
        "mastery": parsed.mastery,
        "move_on_decision": parsed.move_on_decision,
    }


def append_mastery_to_memory(topic: str, eval_block: str, base_dir: Path | str = ".") -> Path:
    """
    Append the evaluation summary into docs/memory.md with a dated heading.
    """
    memory_path = Path(base_dir) / "docs" / "memory.md"
    memory_path.parent.mkdir(parents=True, exist_ok=True)

    heading = f"\n\n## Mastery Check — {date.today().isoformat()} — {topic.strip()}\n"
    body = eval_block.strip() if eval_block.strip() else "No evaluation block provided."

    with memory_path.open("a", encoding="utf-8") as file:
        file.write(heading)
        file.write(body)
        file.write("\n")

    return memory_path
