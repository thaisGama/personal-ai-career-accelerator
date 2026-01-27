"""Pure parsing helpers for quiz content."""

from __future__ import annotations

import re
from typing import List, Tuple


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


__all__ = ["parse_quiz_sections", "parse_questions"]
