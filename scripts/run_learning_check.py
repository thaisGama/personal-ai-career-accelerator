"""Quick smoke script to generate a micro-quiz."""

from __future__ import annotations

import os
from pathlib import Path

from src.agent.learning_check import generate_micro_quiz
from src.agent.weekly_planner import DEFAULT_MODEL


def main() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        print("Set OPENAI_API_KEY before running this script.")
        return

    base_dir = Path(__file__).resolve().parents[1]
    topic = "Embeddings"
    context = "Focus on definitions, cosine similarity intuition, and common pitfalls."

    result = generate_micro_quiz(
        topic=topic,
        context_text=context,
        model=DEFAULT_MODEL,
        base_dir=base_dir,
    )

    print("Quiz generated.")
    print(f"Path: {result['quiz_path']}")
    print("Preview:")
    print(result["quiz_markdown"])


if __name__ == "__main__":
    main()
