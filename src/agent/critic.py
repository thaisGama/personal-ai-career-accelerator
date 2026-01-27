"""Read-only critic for weekly plan quality checks."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

from .weekly_planner import call_llm


def parse_critic_report(text: str) -> Dict[str, Any]:
    report_text = text.strip()
    if "<<CRITIC_REPORT>>" in report_text and "<<END_CRITIC_REPORT>>" in report_text:
        report_text = report_text.split("<<CRITIC_REPORT>>", 1)[1]
        report_text = report_text.split("<<END_CRITIC_REPORT>>", 1)[0]
        report_text = report_text.strip()

    status = "UNKNOWN"
    violations: List[Dict[str, str]] = []
    patch_list: List[str] = []

    lines = [line.strip() for line in report_text.splitlines() if line.strip()]
    section = None
    for line in lines:
        lowered = line.lower()
        if lowered.startswith("status:"):
            status_val = line.split(":", 1)[1].strip().upper()
            if status_val in {"PASS", "FAIL"}:
                status = status_val
            continue
        if lowered.startswith("violations"):
            section = "violations"
            continue
        if lowered.startswith("patch list"):
            section = "patch_list"
            continue
        if not line.startswith("-"):
            continue
        content = line.lstrip("-").strip()
        if section == "patch_list":
            if content:
                patch_list.append(content)
            continue

        match = re.search(r"\[(AMR-[A-Z]\d{3})\]", content)
        if section == "violations" or match:
            violation_id = match.group(1) if match else "UNKNOWN"
            message = content
            if match:
                message = content.replace(match.group(0), "").strip(" -:")
            violations.append({"id": violation_id, "message": message})

    return {
        "status": status,
        "violations": violations,
        "patch_list": patch_list,
    }


def run_plan_critic(weekly_plan_md: str, base_dir: Path, model: str) -> Dict[str, Any]:
    misbehaviors_path = base_dir / "docs" / "misbehaviors.md"
    misbehaviors_text = ""
    if misbehaviors_path.exists():
        misbehaviors_text = misbehaviors_path.read_text(encoding="utf-8")

    system_prompt = (
        "You are a strict read-only plan critic. Review the plan for violations of the "
        "misbehaviors registry. Do NOT rewrite the plan. Output only the report block."
    )
    user_prompt = f"""Misbehaviors registry:
{misbehaviors_text or "None provided."}

Weekly plan:
{weekly_plan_md}

Return ONLY this block:
<<CRITIC_REPORT>>
Status: PASS | FAIL
Violations:
- [AMR-XXX] ...
Patch list:
- ...
<<END_CRITIC_REPORT>>"""

    raw_output = call_llm(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model=model,
        temperature=0.0,
    )
    parsed = parse_critic_report(raw_output)

    return {
        "status": parsed.get("status", "UNKNOWN"),
        "violations": parsed.get("violations", []),
        "patch_list": parsed.get("patch_list", []),
        "raw_critic_output": raw_output,
        "misbehaviors_chars": len(misbehaviors_text),
    }
