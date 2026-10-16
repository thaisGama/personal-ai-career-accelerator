"""Golden API requests captured from production code before prompt extraction.

Fixtures originate at 5f399f0. Never regenerate them to make a refactor pass.
All LLM and embedding boundaries are replaced; no paid requests are made.
"""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.agent import critic, learning_check, react_agent, tools, weekly_planner
from src.agent.learner_setup import make_learner_setup
from src.agent.learning_progress_store import append_week_from_plan, update_day_learning_unit_path
from src.agent.task_store import TaskProgressSummary

FIXTURE = Path(__file__).parent / "fixtures" / "prompts" / "production_requests.json"
SPECIAL = 'Practical RAG — {literal} $value\nSecond line  '
PLAN = '# Week 2 Learning Plan\n\n🧩 Learning Days (10–30 min)\n- 🔥 **Day 1 (20 min): Retrieval** [phase:P1][milestone:M1.1][depth:intro]'


def collect_requests(root, monkeypatch):
    requests = {}

    def capture(module, name, response='snapshot output'):
        requests[name] = []

        def fake(system_prompt, user_prompt, **options):
            requests[name].append(dict(system=system_prompt, user=user_prompt, **options))
            return response

        monkeypatch.setattr(module, 'call_llm', fake)

    monkeypatch.setattr(tools, '_memory_context_for_day', lambda *args, **kw: SPECIAL)
    monkeypatch.setattr(tools.LocalVectorStore, 'embed', lambda *args, **kw: pytest.fail('Unexpected embedding call'))
    summary = TaskProgressSummary(
        counts_by_status={'DONE': 1},
        open_tasks=[dict(title=SPECIAL, task_id='t1', status='NEEDS_REVIEW', priority=1, evidence_score=0.4)],
        weak_topics=['retrieval', SPECIAL], completed_last_week=['Embeddings', SPECIAL],
    )
    for filled in (False, True):
        label = 'populated' if filled else 'empty'
        kwargs = dict(goal=SPECIAL, time_per_week_hours=2.5, max_session_minutes=25,
                      preferences=SPECIAL if filled else None, memory_context=SPECIAL if filled else '',
                      memory_used=filled, memory_source='docs/memory.md', memory_char_count=len(SPECIAL) if filled else 0,
                      task_progress=summary if filled else None, roadmap_context=SPECIAL if filled else None,
                      roadmap_progress='Progress: 2/5' if filled else None, week_number=2 if filled else None,
                      target_level='hardcore' if filled else None, background=SPECIAL if filled else None)
        requests['weekly_' + label] = weekly_planner.build_weekly_planner_prompt(**kwargs)
        requests['unit_' + label] = weekly_planner.build_learning_unit_prompt(
            goal=SPECIAL, preferences=kwargs['preferences'], memory_context=kwargs['memory_context'],
            roadmap_tags='[phase:P1][milestone:M1.1]' if filled else None,
            roadmap_context=kwargs['roadmap_context'], plan_context=SPECIAL if filled else None,
            target_level=kwargs['target_level'], background=kwargs['background'], target_role=SPECIAL if filled else None)
        requests['controller_' + label] = react_agent.build_react_controller_prompt(
            SPECIAL, 2.5, 25, {'text': SPECIAL} if filled else {},
            {'memory_used': True, 'memory_attempted': True, 'memory_hits': 2, 'roadmap_exists': True,
             'weekly_plan_md': SPECIAL, 'weak_topics': [SPECIAL], 'weekly_plan_path': 'plan.md',
             'linkedin_path': 'post.md', 'next_task': 't1'} if filled else {}, SPECIAL)
        capture(learning_check, 'quiz_' + label)
        learning_check.generate_micro_quiz(SPECIAL, SPECIAL if filled else None,
                                          [dict(task_id='t1', title=SPECIAL, topic='RAG')] if filled else None,
                                          model='snapshot-model', base_dir=root)
        capture(learning_check, 'grading_' + label)
        learning_check.evaluate_micro_quiz(SPECIAL, SPECIAL, SPECIAL if filled else '', model='snapshot-model')
        registry = root / 'docs' / 'misbehaviors.md'
        if filled:
            registry.parent.mkdir(parents=True, exist_ok=True)
            registry.write_text(SPECIAL, encoding='utf-8')
        capture(critic, 'critic_' + label)
        critic.run_plan_critic(SPECIAL, root, 'snapshot-model')
        capture(tools, 'roadmap_' + label, '{}')
        setup = make_learner_setup(goal=SPECIAL, hours_per_week=2.5, max_session_minutes=30,
                                  learning_intensity='medium', background='', preferences='')
        tools.tool_generate_learning_roadmap(SPECIAL, 'medium', SPECIAL if filled else None,
                                             None, root, 'snapshot-model', setup)

    class RetryCaptured(Exception):
        pass

    requests['controller_invalid_json'] = []

    def invalid_then_stop(system_prompt, user_prompt, **options):
        requests['controller_invalid_json'].append(dict(system=system_prompt, user=user_prompt, **options))
        if len(requests['controller_invalid_json']) == 2:
            raise RetryCaptured
        return 'not JSON'

    monkeypatch.setattr(react_agent, 'call_llm', invalid_then_stop)
    with pytest.raises(RetryCaptured):
        react_agent.run_weekly_planner_agent_react(SPECIAL, 2, 30, {}, 'snapshot-model', root)

    quality = dict(ok=False, issues=['Missing exercise', SPECIAL], missing_definitions=['retrieval', SPECIAL])
    monkeypatch.setattr(weekly_planner, 'check_learning_unit_quality', lambda _: quality)
    monkeypatch.setattr(tools, 'check_learning_unit_quality', lambda _: quality)
    capture(weekly_planner, 'weekly_generation_and_repair',
            f'<<PLAN_MARKDOWN>>{PLAN}\n<<END_PLAN>>\n<<MEMORY_SNIPPET>>Memory\n<<END_MEMORY>>')
    weekly_planner.generate_weekly_plan_and_learning_unit(
        SPECIAL, 2.5, 25, None, SPECIAL, True, 'docs/memory.md', len(SPECIAL), week_number=2, model='snapshot-model')

    progress_path = root / 'data' / 'learning_progress.json'
    append_week_from_plan(progress_path, PLAN, roadmap_id='rag', phase_id='P1', milestone_id='M1.1',
                          week_number_global=2, goal=SPECIAL)
    # Exercise normal days, reviews, and quiz context with/without saved learning material.
    capture(tools, 'day_quiz_without_material')
    tools.tool_generate_quiz_for_day('day_001', root, 'snapshot-model')
    material = root / 'docs' / 'learning_units' / 'material.md'
    material.parent.mkdir(parents=True, exist_ok=True)
    material.write_text(SPECIAL, encoding='utf-8')
    update_day_learning_unit_path(progress_path, 'day_001', 'docs/learning_units/material.md')
    capture(tools, 'day_quiz_with_material')
    tools.tool_generate_quiz_for_day('day_001', root, 'snapshot-model')
    for review in (False, True):
        if review:
            progress = json.loads(progress_path.read_text())
            progress['weeks'][0]['days'][0].update(is_review=True, review_of_day_id='day_000',
                                                  review_reason=SPECIAL, quiz_result='FAIL', reflection=SPECIAL)
            progress_path.write_text(json.dumps(progress), encoding='utf-8')
        capture(tools, 'day_unit_review' if review else 'day_unit')
        tools.tool_generate_learning_unit_for_day('day_001', root, 'snapshot-model')
    return requests


def test_production_requests_match_pre_extraction_snapshot(tmp_path, monkeypatch):
    # Normalize only JSON tuples to lists, never prompt whitespace or content.
    actual = json.loads(json.dumps(collect_requests(tmp_path, monkeypatch), ensure_ascii=False))
    assert actual == json.loads(FIXTURE.read_text(encoding='utf-8'))
