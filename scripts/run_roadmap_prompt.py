"""One-shot roadmap prompt experiment, isolated from application persistence."""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.learner_setup import make_learner_setup, validate_learner_setup
from src.agent.learning_purpose import PURPOSE_LABELS
from src.agent.tools import build_roadmap_prompt, parse_roadmap_output
from src.agent.weekly_planner import call_llm


def run_experiment(learner_setup: dict, model: str) -> dict:
    """Make one production-client request; return diagnostics without application writes."""
    setup = validate_learner_setup(learner_setup)
    prompt = build_roadmap_prompt(setup["goal"], setup["learning_intensity"], setup["background"], setup)
    metadata = {"model": None, "usage": None}
    result = {
        "stage": "roadmap",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "learner_setup": setup,
        "requested_model": model,
        "response_metadata": metadata,
        "prompt": prompt,
        "raw_response": None,
        "roadmap": None,
        "validation_errors": [],
        "error": None,
    }
    try:
        # Keep the wrapper's existing usage log off the JSON report's stdout.
        with redirect_stdout(sys.stderr):
            raw = call_llm(
                system_prompt=prompt["system"], user_prompt=prompt["user"], model=model,
                max_retries=0, response_metadata=metadata,
            )
    except Exception as exc:
        result["error"] = str(exc)
        return result

    result["raw_response"] = raw
    try:
        parsed = parse_roadmap_output(raw, setup)
    except (TypeError, ValueError, KeyError, AttributeError) as exc:
        # Retain even malformed field types that the production validator cannot inspect.
        result["error"] = f"Roadmap validation failed: {exc}"
        result["validation_errors"] = [result["error"]]
        return result
    result["roadmap"] = parsed.get("roadmap")
    result["error"] = parsed.get("error")
    result["validation_errors"] = parsed.get("validation_errors", [parsed["error"]] if "error" in parsed else [])
    return result


def output_path(name: str) -> Path:
    """Allow only a new JSON filename under the dedicated experiment directory."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.json", name):
        raise ValueError("--save must be a simple .json filename, not a path.")
    directory = PROJECT_ROOT.resolve() / "experiments" / "roadmap_prompts"
    if directory.resolve() != directory:
        raise ValueError("The experiment directory must not redirect through a symlink.")
    path = directory / name
    if path.exists() or path.is_symlink():
        raise ValueError(f"Experiment already exists: {path}. Choose a new filename.")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--goal", required=True)
    parser.add_argument("--learning-purpose", choices=list(PURPOSE_LABELS), required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--weekly-hours", type=float, default=2.0)
    parser.add_argument("--max-session-minutes", type=int, choices=[10, 15, 20, 30, 45, 60], default=30)
    parser.add_argument("--intensity", choices=["light", "medium", "hardcore"], default="medium")
    parser.add_argument("--background", default="")
    parser.add_argument("--preferences", default="")
    parser.add_argument("--save", metavar="NAME.json", help="Save a new report in experiments/roadmap_prompts/.")
    args = parser.parse_args(argv)
    try:
        setup = make_learner_setup(
            goal=args.goal, learning_purpose=args.learning_purpose,
            background=args.background, preferences=args.preferences,
            hours_per_week=args.weekly_hours, max_session_minutes=args.max_session_minutes,
            learning_intensity=args.intensity,
        )
        if not args.model.strip():
            raise ValueError("Model must not be empty.")
        destination = output_path(args.save) if args.save else None
    except ValueError as exc:
        parser.error(str(exc))

    # Reserve a new output before spending a request; never overwrite existing files.
    try:
        if destination:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("x", encoding="utf-8") as file:
                result = run_experiment(setup, args.model)
                report = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
                print(report, end="")
                file.write(report)
        else:
            result = run_experiment(setup, args.model)
            print(json.dumps(result, ensure_ascii=False, indent=2))
    except OSError as exc:
        print(f"Could not save experiment: {exc}", file=sys.stderr)
        return 2
    return 1 if result["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
