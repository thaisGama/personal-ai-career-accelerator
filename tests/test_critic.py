"""Tests for critic report parsing."""

from pathlib import Path

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.critic import parse_critic_report


def test_parse_critic_report_pass():
    text = """<<CRITIC_REPORT>>
Status: PASS
Violations:
- [AMR-R001] No tool loops detected.
Patch list:
- None
<<END_CRITIC_REPORT>>"""
    parsed = parse_critic_report(text)

    assert parsed["status"] == "PASS"
    assert parsed["violations"][0]["id"] == "AMR-R001"
    assert parsed["patch_list"] == ["None"]


def test_parse_critic_report_fail_with_two_violations():
    text = """<<CRITIC_REPORT>>
Status: FAIL
Violations:
- [AMR-R003] Missing output markers.
- [AMR-R005] Micro-tasks missing done-checks.
Patch list:
- Add required markers for plan output.
- Rewrite micro-tasks with artifact + done-check.
<<END_CRITIC_REPORT>>"""
    parsed = parse_critic_report(text)

    assert parsed["status"] == "FAIL"
    assert len(parsed["violations"]) == 2
    assert parsed["violations"][0]["id"] == "AMR-R003"
    assert parsed["violations"][1]["id"] == "AMR-R005"
    assert len(parsed["patch_list"]) == 2


def test_parse_critic_report_missing_tags():
    text = """Status: FAIL
Violations:
- [AMR-R004] Next actions missing.
Patch list:
- Add Next Actions section."""
    parsed = parse_critic_report(text)

    assert parsed["status"] == "FAIL"
    assert parsed["violations"][0]["id"] == "AMR-R004"
