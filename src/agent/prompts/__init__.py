"""Local, versioned prompt templates. Rendering never trims or normalizes text."""

import hashlib
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_VERSIONS = json.loads((_ROOT / "versions.json").read_text(encoding="utf-8"))


def _template_bytes(prompt_id: str) -> bytes:
    # Resolve only registered IDs; callers cannot supply arbitrary file paths.
    if prompt_id not in _VERSIONS:
        raise KeyError(f"Unknown prompt ID: {prompt_id}")
    return (_ROOT / "templates" / (prompt_id.replace(".", "/") + ".txt")).read_bytes()


def render_prompt(prompt_id: str, **variables: object) -> str:
    """Substitute named variables once; preserve literal braces and whitespace."""
    return _template_bytes(prompt_id).decode("utf-8").format_map(variables)


def get_prompt_metadata(prompt_id: str) -> dict[str, str]:
    """Return JSON-serializable identity for future evaluation callers to record."""
    content = _template_bytes(prompt_id)
    return {
        "prompt_id": prompt_id,
        "version": _VERSIONS[prompt_id],
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def list_prompt_metadata() -> list[dict[str, str]]:
    """List all templates in stable ID order, including context and retry variants."""
    return [get_prompt_metadata(prompt_id) for prompt_id in sorted(_VERSIONS)]
