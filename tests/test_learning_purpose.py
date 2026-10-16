"""Learning Purpose MVP across shared generation and day completion, no paid calls."""
import copy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.agent import learning_check, react_agent, tools, weekly_planner
from src.agent.learner_setup import load_learner_setup, make_learner_setup, validate_learner_setup
from src.agent.learning_purpose import LEGACY_PURPOSE, PURPOSE_LABELS, purpose_context
from src.agent.learning_progress_store import append_week_from_plan, load_learning_progress, update_day_learning_unit_path
from src.agent.prompts import render_prompt
from src.core.services.planner_service import run_weekly_planner_service
from src.core.services.quiz_service import generate_day_quiz_service, evaluate_day_quiz_service
from test_roadmap_learner_setup import CURRICULUM, service, mocked_content

PURPOSES = list(PURPOSE_LABELS)
QUIZ = '<<QUIZ>>\nSelected day\nQ1) Apply the concept.\n<<ANSWER_KEY>>\nQ1: Correct explanation.\n<<RUBRIC>>\nClear.'
EVAL = '<<EVAL>>\n- Score: 9/10\n- Mastery: SOLID\n- Move-on decision: MOVE_ON\n<<END_EVAL>>'
PLAN = '# Week 1 Learning Plan\n\n🧩 Learning Days (10–30 min)\n- 🔥 **Day 1 (10 min): Focus** [phase:P1][milestone:M1.1]'


def setup(purpose=LEGACY_PURPOSE, **changes):
    return make_learner_setup(**dict(dict(goal='Become an AI Engineer', background='Background', preferences='Examples',
                                         hours_per_week=0.5, max_session_minutes=10, learning_intensity='light',
                                         learning_purpose=purpose), **changes))


@pytest.fixture(autouse=True)
def no_embeddings(monkeypatch):
    monkeypatch.setattr(tools.LocalVectorStore, 'embed', lambda *a, **kw: pytest.fail('Paid embedding call'))
    monkeypatch.setattr(tools.LocalVectorStore, 'search', lambda *a, **kw: [])


@pytest.mark.parametrize('purpose', PURPOSES)
@pytest.mark.parametrize('agent', [False, True])
def test_routes_persist_restore_purpose_without_rewriting_roadmap(tmp_path, monkeypatch, mocked_content, purpose, agent):
    result = service(tmp_path, agent, learning_purpose=purpose)
    path = tmp_path / 'roadmaps' / 'distinct_submitted_goal_roadmap.json'
    roadmap = json.loads(path.read_text())
    assert roadmap['learner_setup']['learning_purpose'] == purpose
    assert 'learning_purpose: ' + purpose in path.with_suffix('.md').read_text()
    assert len(roadmap['phases']) == len(roadmap['phases'][0]['milestones']) == 1
    assert Path(result['result']['plan_path']).is_file()
    before = path.read_bytes()
    received = []
    monkeypatch.setattr(react_agent, 'run_weekly_planner_agent_react', lambda **kw: received.append(kw) or {})
    monkeypatch.setattr(weekly_planner, 'generate_and_save_week', lambda **kw: received.append(kw) or {})
    service(tmp_path, agent, learning_purpose='topic_mastery', roadmap_id='distinct_submitted_goal')
    forwarded = received[0]['preferences']['learner_setup'] if agent else received[0]['learner_setup']
    assert forwarded == roadmap['learner_setup']
    assert path.read_bytes() == before


@pytest.mark.parametrize('agent', [False, True])
def test_legacy_roadmap_restores_career_default_without_disk_migration(tmp_path, monkeypatch, agent):
    original = setup()
    del original['learning_purpose']
    path = tmp_path / 'roadmaps' / 'legacy_roadmap.json'
    path.parent.mkdir()
    path.write_text(json.dumps(dict(CURRICULUM, learner_setup=original)))
    before = path.read_bytes()
    assert load_learner_setup(tmp_path, 'legacy') == dict(original, learning_purpose=LEGACY_PURPOSE)
    received = []
    monkeypatch.setattr(react_agent, 'run_weekly_planner_agent_react', lambda **kw: received.append(kw) or {})
    monkeypatch.setattr(weekly_planner, 'generate_and_save_week', lambda **kw: received.append(kw) or {})
    service(tmp_path, agent, learning_purpose='certification_preparation', roadmap_id='legacy')
    forwarded = received[0]['preferences']['learner_setup'] if agent else received[0]['learner_setup']
    assert forwarded['learning_purpose'] == LEGACY_PURPOSE
    assert forwarded['hours_per_week'] == 0.5 and forwarded['max_session_minutes'] == 10
    assert path.read_bytes() == before


@pytest.mark.parametrize('purpose', PURPOSES)
@pytest.mark.parametrize('goal', ['Become an AI Engineer', 'Master IAM policies', 'Become a data analyst'])
def test_roadmap_template_selection_and_application_owned_purpose(tmp_path, monkeypatch, purpose, goal):
    captured = []
    content = copy.deepcopy(CURRICULUM)
    content['learner_setup'] = setup('topic_mastery')  # Model must not override application intent.
    monkeypatch.setattr(tools, 'call_llm', lambda **kw: captured.append(kw) or json.dumps(content))
    selected = setup(purpose, goal=goal)
    result = tools.tool_generate_learning_roadmap(goal, 'light', '', 'selected', tmp_path, 'mock', selected)
    assert 'error' not in result
    request = captured[0]
    is_ai = purpose == 'career_development' and 'AI Engineer' in goal
    assert ('MANDATORY AI ENGINEER SPINE' in request['system_prompt']) == is_ai
    if is_ai:
        assert request['system_prompt'] == render_prompt('roadmap.system')
    else:
        assert request['system_prompt'] == render_prompt('roadmap.focused_system')
        assert 'One phase with one milestone' in request['system_prompt']
    assert request['user_prompt'].endswith(purpose_context(selected))
    assert result['roadmap']['learner_setup'] == selected
    assert len(result['roadmap']['phases']) == 1


@pytest.mark.parametrize('purpose', PURPOSES)
def test_shared_weekly_and_unit_generation_receive_purpose_and_time_limits(monkeypatch, purpose):
    selected = setup(purpose)
    requests = []
    monkeypatch.setattr(weekly_planner, 'check_learning_unit_quality', lambda _: {'ok': True})
    def generate(**kw):
        requests.append(kw)
        return f'<<PLAN_MARKDOWN>>{PLAN}\n<<END_PLAN>>' if len(requests) == 1 else '<<LEARNING_UNIT>>Lesson<<END_LEARNING_UNIT>>'
    monkeypatch.setattr(weekly_planner, 'call_llm', generate)
    result = weekly_planner.generate_weekly_plan_and_learning_unit(
        selected['goal'], 0.5, 10, '', '', False, 'memory', 0, learner_setup=selected)
    assert result['learning_unit_md'] == 'Lesson'
    assert len(requests) == 2
    for request in requests:
        assert request['user_prompt'].endswith(purpose_context(selected))
        assert 'Available weekly time: 0.5 hours.' in request['user_prompt']
        assert 'Maximum session length: 10 minutes.' in request['user_prompt']
    assert requests[0]['max_tokens'] == weekly_planner.PLAN_MAX_TOKENS
    assert requests[1]['max_tokens'] == weekly_planner.UNIT_MAX_TOKENS


@pytest.mark.parametrize('purpose', PURPOSES)
@pytest.mark.parametrize('durations,error', [([20], 'session length'), ([10, 10, 10, 10], 'weekly time budget'), ([], 'explicit durations')])
def test_over_budget_or_unparseable_week_is_rejected_before_unit_or_save(monkeypatch, purpose, durations, error):
    days = '\n'.join(f'- **Day {i} ({minutes} min): Topic**' for i, minutes in enumerate(durations, 1))
    response = f'<<PLAN_MARKDOWN>># Week 1\n\n🧩 Learning Days (10–30 min)\n{days}\n<<END_PLAN>>'
    requests = []
    monkeypatch.setattr(weekly_planner, 'call_llm', lambda **kw: requests.append(kw) or response)
    with pytest.raises(ValueError, match=error):
        weekly_planner.generate_weekly_plan_and_learning_unit('Goal', 0.5, 10, '', '', False, 'memory', 0,
                                                             learner_setup=setup(purpose))
    assert len(requests) == 1


@pytest.mark.parametrize('purpose', PURPOSES)
def test_day_unit_quiz_and_grading_use_owning_roadmap_and_preserve_associations(tmp_path, monkeypatch, purpose):
    selected = setup(purpose)
    roadmaps = tmp_path / 'roadmaps'
    roadmaps.mkdir()
    (roadmaps / 'owner_roadmap.json').write_text(json.dumps(dict(CURRICULUM, learner_setup=selected)))
    (roadmaps / 'other_roadmap.json').write_text(json.dumps(dict(CURRICULUM, learner_setup=setup('topic_mastery', goal='UNRELATED'))))
    progress_path = tmp_path / 'data' / 'learning_progress.json'
    append_week_from_plan(progress_path, PLAN, roadmap_id='owner', goal=selected['goal'])
    append_week_from_plan(progress_path, PLAN, roadmap_id='other', goal='UNRELATED')
    monkeypatch.setattr(tools, '_memory_context_for_day', lambda *a, **kw: '')
    monkeypatch.setattr(tools, 'check_learning_unit_quality', lambda _: {'ok': True})
    captured = []
    monkeypatch.setattr(tools, 'call_llm', lambda **kw: captured.append(kw) or '<<LEARNING_UNIT>>DAY MATERIAL<<END_LEARNING_UNIT>>')
    tools.tool_generate_learning_unit_for_day('day_001', tmp_path, 'mock', background='STALE UI')
    assert 'Background / constraints: Background' in captured[0]['user_prompt']
    assert 'STALE UI' not in captured[0]['user_prompt']
    monkeypatch.setattr(tools, 'call_llm', lambda **kw: captured.append(kw) or QUIZ)
    identity = dict(roadmap_id='owner', week_id='week_001', day_id='day_001')
    generated = generate_day_quiz_service(identity=identity, model='mock', base_dir=tmp_path)
    assert 'DAY MATERIAL' in captured[1]['user_prompt']
    monkeypatch.setattr(learning_check, 'call_llm', lambda system_prompt, user_prompt, **kw:
                        captured.append(dict(system_prompt=system_prompt, user_prompt=user_prompt, **kw)) or EVAL)
    evaluate_day_quiz_service(binding=generated['binding'], quiz_markdown=generated['quiz_markdown'],
                              learner_answers='Explanation', model='mock', base_dir=tmp_path)
    assert len(captured) == 3
    for request in captured:
        assert request['user_prompt'].endswith(purpose_context(selected))
        assert 'UNRELATED' not in request['user_prompt']
    progress = load_learning_progress(progress_path)
    assert progress['weeks'][0]['days'][0]['quiz_result'] == 'PASS'
    assert progress['weeks'][1]['days'][0]['quiz_result'] == ''
    assert generated['binding']['roadmap_id'] == 'owner'
    with pytest.raises(ValueError, match='association'):
        tools.tool_evaluate_quiz_for_day('day_001', 'answer', tmp_path, expected_roadmap_id='other')


@pytest.mark.parametrize('value', ['interview_preparation', 'unknown', None, ''])
def test_unsupported_purposes_rejected(value):
    with pytest.raises(ValueError, match='learning_purpose'):
        validate_learner_setup(dict(setup(), learning_purpose=value))


@pytest.mark.parametrize('purpose', PURPOSES)
def test_agent_tool_and_controller_receive_application_setup(tmp_path, monkeypatch, purpose):
    selected = setup(purpose)
    captured = []
    monkeypatch.setattr(tools, 'generate_weekly_plan_and_learning_unit', lambda **kw: captured.append(kw) or {})
    tools.tool_generate_weekly_plan(selected['goal'], 0.5, 10, {'learner_setup': setup('topic_mastery')},
                                    '', {}, 'mock', tmp_path, roadmap=dict(CURRICULUM, learner_setup=selected))
    assert captured[0]['learner_setup'] == selected
    assert captured[0]['time_per_week_hours'] == 0.5
    assert captured[0]['max_session_minutes'] == 10
    _, prompt = react_agent.build_react_controller_prompt(selected['goal'], 0.5, 10,
                                                          {'learner_setup': selected}, {}, '')
    assert prompt.endswith(purpose_context(selected))


def test_same_goal_different_purpose_cannot_silently_reuse_or_overwrite_roadmap(tmp_path):
    path = tmp_path / 'roadmaps' / 'same_roadmap.json'
    path.parent.mkdir()
    path.write_text(json.dumps(dict(CURRICULUM, learner_setup=setup('topic_mastery'))))
    before = path.read_bytes()
    result = tools.tool_load_learning_roadmap('same', tmp_path, learning_purpose='certification_preparation')
    assert 'different learning purpose' in result['error']
    assert path.read_bytes() == before
    assert not tools.tool_load_learning_roadmap('same', tmp_path, force_regenerate=True)['exists']


@pytest.mark.parametrize('purpose', PURPOSES)
def test_purpose_context_matches_reviewed_snapshot(purpose):
    fixture = Path(__file__).parent / 'fixtures' / 'prompts' / 'purpose_contexts.json'
    assert purpose_context(setup(purpose)) == json.loads(fixture.read_text())[purpose]
