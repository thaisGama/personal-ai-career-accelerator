"""Shared roadmap presentation/preferences, with every LLM boundary mocked."""
import copy
import json
from pathlib import Path
import sys

import pytest
from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.agent import tools, weekly_planner
from src.agent.tools import tool_generate_learning_roadmap
from src.agent.learner_setup import (
    load_learner_setup, make_roadmap_learner_setup, validate_learner_setup,
    validate_roadmap_learner_setup,
)
from src.agent.learning_purpose import PURPOSE_LABELS
from standalone_roadmap import service
from test_standalone_roadmap import api, APP, CURRICULUM, INPUTS
from test_roadmap_learner_setup import SETUP


def roadmap_setup(**changes):
    return make_roadmap_learner_setup(**dict(INPUTS, preferences='', **changes))


@pytest.mark.parametrize('preferred', [None, 15, 30, 45, 60, 90])
@pytest.mark.parametrize('purpose', list(PURPOSE_LABELS))
def test_shared_roadmap_preferences_and_purpose(preferred, purpose):
    setup = roadmap_setup(preferred_session_minutes=preferred)
    setup['learning_purpose'] = purpose
    prompt = tools.build_roadmap_prompt(setup['goal'], 'medium', setup['background'], setup)
    assert 'max_session_minutes' not in setup
    assert 'Maximum session length:' not in prompt['user']
    assert 'CONFIGURED TIME LIMITS' not in prompt['user']
    assert f'LEARNING PURPOSE: {PURPOSE_LABELS[purpose]}' in prompt['user']
    assert 'Detailed scheduling belongs to the Weekly Planner.' in prompt['user']
    assert 'not an exhaustive session timetable' in prompt['user']
    expected = 'No preference' if preferred is None else f'{preferred} minutes'
    assert f'Preferred session duration: {expected}.' in prompt['user']
    if preferred is None:
        assert 'No session-duration constraint applies.' in prompt['user']
        assert '30 minutes' not in prompt['user']
    else:
        assert 'soft guidance' in prompt['user'] and 'explain why' in prompt['user']
    assert 'hard maximum' not in prompt['user']
    result = tools.parse_roadmap_output(json.dumps(CURRICULUM), setup)
    assert result['roadmap']['learner_setup'] == setup


@pytest.mark.parametrize('value', [True, False, 0, -15, 10, 20, 120, 30.0, '30', float('nan')])
def test_invalid_preferences_rejected_before_request(api, value):
    constructor, create, _ = api
    with pytest.raises(ValueError, match='preferred_session_minutes'):
        service.generate_roadmap(**INPUTS, preferred_session_minutes=value)
    constructor.assert_not_called()
    create.assert_not_called()


@pytest.mark.parametrize('total,hours,fractional,planning', [
    (15, 4, '3.75', '4 weeks'), (12, 4, '3', '3 weeks'),
    (5, 3.5, '1.43', '2 weeks'), (1, 2, '0.5', '1 week'), (0.001, 2, '<0.01', '1 week'),
])
def test_readable_duration_and_curriculum_preserved(total, hours, fractional, planning):
    roadmap = copy.deepcopy(CURRICULUM)
    roadmap['total_estimated_hours'] = total
    roadmap['phases'][0]['estimated_hours'] = total
    milestone = roadmap['phases'][0]['milestones'][0]
    milestone.update(estimated_hours=total, deliverables=['A working policy'],
                     suggested_practice=['Practice A', 'Practice B', 'Practice C', 'Practice D', 'Practice E'],
                     resources=[dict(title='IAM docs', owner='AWS', platform='Documentation', search_phrase='IAM policy')])
    roadmap['estimated_weeks_at_hours_per_week'] = {str(h): total / h for h in (2, 5, 7)}
    roadmap['learner_setup'] = roadmap_setup()
    roadmap['learner_setup']['hours_per_week'] = hours
    before = copy.deepcopy(roadmap)
    assert tools._validate_roadmap_schema(roadmap) == (True, [])
    markdown = tools._render_roadmap_markdown(roadmap)
    assert f'Calculated duration: {fractional} weeks' in markdown
    assert f'Planning estimate: approximately {planning}' in markdown
    assert 'Estimated weeks at 2/5/7 hrs per week:' in markdown
    for value in ['Understand permissions', 'Explain deny precedence', 'A working policy',
                  'Practice A', 'Practice E', 'IAM docs - AWS - Documentation']:
        assert value in markdown
    for value in ['learner_setup', 'hours_per_week', 'max_session_minutes', 'preferred_session_minutes',
                  'learning_purpose', 'Basic AWS', '## Learner setup']:
        assert value not in markdown
    assert roadmap == before


def test_both_entry_points_use_same_renderer_and_keep_full_app_state(api, tmp_path, monkeypatch):
    render = tools._render_roadmap_markdown
    assert service._render_roadmap_markdown is render
    rendered = []

    def spy(roadmap):
        result = render(roadmap)
        rendered.append((copy.deepcopy(roadmap), result))
        return result

    monkeypatch.setattr(service, '_render_roadmap_markdown', spy)
    monkeypatch.setattr(tools, '_render_roadmap_markdown', spy)
    markdown = service.generate_roadmap(**INPUTS)
    # The standalone fixture forbids persistence. Restore only full-app task seeding.
    seeded = []
    monkeypatch.setattr(tools, '_seed_roadmap_tasks', lambda *args: seeded.append(args) or 1)
    monkeypatch.setattr(tools, 'call_llm', lambda **kw: json.dumps(CURRICULUM))
    result = tool_generate_learning_roadmap(
        SETUP['goal'], 'medium', '', 'existing', tmp_path, 'mock', SETUP)
    assert markdown == rendered[0][1]
    assert Path(result['markdown_path']).read_text() == rendered[1][1]
    assert result['roadmap']['learner_setup'] == SETUP
    assert seeded[0][0] == result['roadmap'] and result['seeded_tasks'] == 1
    assert load_learner_setup(tmp_path, 'existing') == SETUP
    assert 'Maximum session duration: 45 minutes' in rendered[1][1]
    assert 'Preferred session duration:' not in rendered[1][1]


def test_legacy_setup_without_purpose_remains_readable(tmp_path):
    setup = dict(SETUP)
    setup.pop('learning_purpose')
    roadmap = dict(CURRICULUM, learner_setup=setup)
    root = tmp_path / 'roadmaps'
    root.mkdir()
    path = root / 'legacy_roadmap.json'
    path.write_text(json.dumps(roadmap))
    before = path.read_bytes()
    assert load_learner_setup(tmp_path, 'legacy')['learning_purpose'] == 'career_development'
    assert 'Learning purpose: Career Development' in tools._render_roadmap_markdown(roadmap)
    assert path.read_bytes() == before


def test_preference_never_substitutes_for_weekly_hard_maximum(monkeypatch):
    setup = dict(SETUP, max_session_minutes=15, preferred_session_minutes=90)
    assert validate_learner_setup(setup) == setup
    assert validate_roadmap_learner_setup(setup) == setup
    for missing in [roadmap_setup(), dict(setup, max_session_minutes=None)]:
        with pytest.raises(ValueError, match='max_session_minutes'):
            validate_learner_setup(missing)
    requests = []
    def generate(**kw):
        requests.append(kw)
        return '<<PLAN_MARKDOWN>># Week 1\n\n🧩 Learning Days (10–30 min)\n- **Day 1 (30 min): Work**\n<<END_PLAN>>'
    monkeypatch.setattr(weekly_planner, 'call_llm', generate)
    with pytest.raises(ValueError, match='maximum session length'):
        weekly_planner.generate_weekly_plan_and_learning_unit(
            setup['goal'], 3.5, 15, '', '', False, 'memory', 0, learner_setup=setup)
    assert len(requests) == 1
    assert 'Maximum session length: 15 minutes.' in requests[0]['user_prompt']


def test_form_preference_default_and_selected_value_reach_generation(api):
    _, create, _ = api
    app = AppTest.from_file(APP).run()
    preference = next(widget for widget in app.selectbox if widget.label == 'Preferred session duration (optional)')
    assert preference.value is None
    assert preference.options == ['No preference', '15 minutes', '30 minutes', '45 minutes', '60 minutes', '90 minutes']
    assert any('Some practical exercises may benefit from longer sessions' in caption.value for caption in app.caption)
    preference.select(90)
    app.text_area[0].input('Learn IAM policies')
    app.button[0].click().run()
    assert not app.exception and not app.error
    assert 'Preferred session duration: 90 minutes' in app.markdown[0].value
    assert 'Preferred session duration: 90 minutes.' in create.call_args.kwargs['messages'][1]['content']
    assert app.session_state['roadmap_markdown'].strip() == app.markdown[0].value


@pytest.mark.parametrize('setup,error', [
    (roadmap_setup(), 'max_session_minutes'),
    (roadmap_setup(preferred_session_minutes=90), 'max_session_minutes'),
    ({key: value for key, value in SETUP.items() if key != 'max_session_minutes'}, 'max_session_minutes'),
    *[(dict(SETUP, max_session_minutes=value), 'max_session_minutes')
      for value in (None, True, False, 0, -30, 22, 90, 30.0, '30')],
    ({key: value for key, value in SETUP.items() if key != 'background'}, 'background'),
    (dict(SETUP, hours_per_week=0), 'hours_per_week'),
    (dict(SETUP, learning_intensity='invalid'), 'learning_intensity'),
])
def test_full_app_persistence_requires_complete_planner_setup(tmp_path, monkeypatch, setup, error):
    def forbidden(*args, **kwargs):
        pytest.fail('Invalid full-app setup must fail before generation or task seeding')

    monkeypatch.setattr(tools, 'call_llm', forbidden)
    monkeypatch.setattr(tools, '_seed_roadmap_tasks', forbidden)
    with pytest.raises(ValueError, match=error):
        tool_generate_learning_roadmap(
            SETUP['goal'], 'medium', '', 'invalid', tmp_path, 'mock', setup)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('setup,labels', [
    (roadmap_setup(), ['Preferred session duration: No preference']),
    (roadmap_setup(preferred_session_minutes=45), ['Preferred session duration: 45 minutes']),
    (SETUP, ['Maximum session duration: 45 minutes']),
    (dict(SETUP, preferred_session_minutes=None), ['Maximum session duration: 45 minutes']),
    (dict(SETUP, preferred_session_minutes=30), [
        'Preferred session duration: 30 minutes', 'Maximum session duration: 45 minutes']),
])
def test_renderer_displays_only_applicable_session_settings(setup, labels):
    roadmap = dict(CURRICULUM, learner_setup=setup)
    before = copy.deepcopy(roadmap)
    markdown = tools._render_roadmap_markdown(roadmap)
    session_lines = [line.removeprefix('- ') for line in markdown.splitlines()
                     if line.startswith(('- Preferred session duration:', '- Maximum session duration:'))]
    assert session_lines == labels
    assert 'Weekly planner session maximum:' not in markdown
    assert 'Calculated duration: 1.43 weeks' in markdown
    assert 'Planning estimate: approximately 2 weeks' in markdown
    assert 'Estimated weeks at 2/5/7 hrs per week: 3 / 1 / 1' in markdown
    assert roadmap == before


def test_standalone_no_preference_still_generates_valid_shared_output(api):
    _, create, _ = api
    markdown = service.generate_roadmap(**INPUTS)
    assert 'Preferred session duration: No preference' in markdown
    assert 'Maximum session duration:' not in markdown
    assert 'Maximum session length:' not in create.call_args.kwargs['messages'][1]['content']
    create.assert_called_once()


@pytest.mark.parametrize('purpose', list(PURPOSE_LABELS))
@pytest.mark.parametrize('maximum', [10, 15, 20, 30, 45, 60])
def test_full_app_roadmap_prompt_respects_configured_hard_maximum(purpose, maximum):
    setup = dict(SETUP, learning_purpose=purpose, max_session_minutes=maximum)
    prompt = tools.build_roadmap_prompt(setup['goal'], setup['learning_intensity'], setup['background'], setup)
    assert f'Maximum session duration: {maximum} minutes (hard maximum).' in prompt['user']
    assert 'Suggested practice activities must fit this maximum.' in prompt['user']
    assert 'Split longer exercises and projects into activities within the limit' in prompt['user']
    assert 'do not recommend exceeding it' in prompt['user']
    assert 'Detailed scheduling belongs to the Weekly Planner.' in prompt['user']
    assert 'not an exhaustive session timetable' in prompt['user']
    assert 'Preferred session duration:' not in prompt['user']
    assert 'soft guidance' not in prompt['user']
    assert 'No session-duration constraint applies.' not in prompt['user']


def test_roadmap_hard_maximum_takes_precedence_over_explicit_preference():
    setup = dict(SETUP, max_session_minutes=15, preferred_session_minutes=90)
    prompt = tools.build_roadmap_prompt(setup['goal'], setup['learning_intensity'], '', setup)
    assert 'Maximum session duration: 15 minutes (hard maximum).' in prompt['user']
    assert 'takes precedence over any session preference' in prompt['user']
    assert '90 minutes' not in prompt['user']
    assert 'Longer practical activities may be recommended' not in prompt['user']
