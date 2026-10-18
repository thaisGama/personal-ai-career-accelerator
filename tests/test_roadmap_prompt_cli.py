"""One-shot CLI requests through the shared client; all network calls are mocked."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import run_roadmap_prompt as cli
from src.agent import tools, weekly_planner
from src.agent.learner_setup import make_learner_setup
from src.agent.prompts import get_prompt_metadata
from test_roadmap_learner_setup import CURRICULUM


@pytest.fixture
def experiment(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, 'PROJECT_ROOT', tmp_path)
    monkeypatch.setenv('OPENAI_API_KEY', 'fake-test-key')
    response = SimpleNamespace(model='returned-model', usage=SimpleNamespace(
        prompt_tokens=120, completion_tokens=80, total_tokens=200),
        choices=[SimpleNamespace(message=SimpleNamespace(content=f'<<ROADMAP_JSON>>\n{json.dumps(CURRICULUM)}\n<<END_ROADMAP_JSON>>'))])
    client = Mock()
    client.chat.completions.create.return_value = response
    constructor = Mock(return_value=client)
    monkeypatch.setattr(weekly_planner, 'OpenAI', constructor)

    def forbidden(*args, **kwargs):
        pytest.fail('Application persistence, downstream generation, or embeddings must not run')

    for name in ('tool_generate_learning_roadmap', '_seed_roadmap_tasks', 'tool_generate_weekly_plan',
                 'tool_generate_learning_unit_for_day', 'tool_generate_quiz_for_day'):
        monkeypatch.setattr(tools, name, forbidden)
    monkeypatch.setattr(tools.LocalVectorStore, '__init__', forbidden)
    monkeypatch.setattr(weekly_planner, 'generate_weekly_plan_and_learning_unit', forbidden)
    for relative in ('roadmaps/saved_roadmap.json', 'data/tasks.csv', 'data/learning_progress.json',
                     'data/memory_vectors.json', 'docs/memory.md', 'weekly_plans/saved.md', 'posts/saved.md'):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'Existing application state\n')
    return tmp_path, constructor, client.chat.completions.create, response


def arguments(purpose='topic_mastery', goal='Master IAM policies', **updates):
    flags = dict(goal=goal, learning_purpose=purpose, model='gpt-6-luna', weekly_hours='0.5',
                 max_session_minutes='10', background='Background {literal}', preferences='Practical examples',
                 intensity='light')
    flags.update(updates)
    return [value for key, value in flags.items() for value in ('--' + key.replace('_', '-'), value)]


def files(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('purpose,goal,system_id', [
    ('certification_preparation', 'AWS certification', 'roadmap.focused_system'),
    ('topic_mastery', 'Master IAM policies', 'roadmap.focused_system'),
    ('career_development', 'Become an AI Engineer', 'roadmap.system'),
    ('career_development', 'Become a data analyst', 'roadmap.focused_system'),
])
def test_cli_one_request_matches_production_prompts_and_captures_metadata(experiment, capsys, purpose, goal, system_id):
    root, constructor, create, response = experiment
    before = files(root)
    assert cli.main(arguments(purpose, goal)) == 0
    stdout, stderr = capsys.readouterr()
    report = json.loads(stdout)
    assert files(root) == before
    constructor.assert_called_once_with(api_key='fake-test-key', max_retries=0)
    assert create.call_count == 1
    assert create.call_args.kwargs['reasoning_effort'] == 'none'
    assert create.call_args.kwargs['max_completion_tokens'] == weekly_planner.MAX_TOKENS
    assert create.call_args.kwargs['temperature'] == 0.5
    setup = make_learner_setup(goal=goal, learning_purpose=purpose, background='Background {literal}',
                              preferences='Practical examples', hours_per_week=0.5, max_session_minutes=10,
                              learning_intensity='light')
    production_prompt = tools.build_roadmap_prompt(goal, 'light', setup['background'], setup)
    assert report['prompt'] == production_prompt
    assert create.call_args.kwargs['messages'] == [
        {'role': 'system', 'content': report['prompt']['system']},
        {'role': 'user', 'content': report['prompt']['user']},
    ]
    assert report['prompt']['templates'] == [get_prompt_metadata(prompt_id) for prompt_id in (
        system_id, 'roadmap.user', 'purpose.context', 'purpose.' + purpose)]
    assert report['raw_response'] == response.choices[0].message.content
    assert report['roadmap'] == dict(CURRICULUM, learner_setup=setup)
    assert report['learner_setup'] == setup
    assert report['response_metadata'] == dict(model='returned-model', usage=dict(
        prompt_tokens=120, completion_tokens=80, total_tokens=200))
    assert report['validation_errors'] == [] and report['error'] is None
    assert 'Token usage' in stderr  # Usage logging never corrupts stdout JSON.


def test_save_is_separate_from_application_state_and_never_overwrites(experiment, capsys):
    root, _constructor, create, _response = experiment
    before = files(root)
    args = arguments(save='version-1.json')
    assert cli.main(args) == 0
    report = json.loads(capsys.readouterr().out)
    after = files(root)
    name = 'experiments/roadmap_prompts/version-1.json'
    saved_bytes = after[name]
    assert json.loads(after.pop(name)) == report
    assert after == before
    create.reset_mock()
    with pytest.raises(SystemExit) as exc:
        cli.main(args)
    assert exc.value.code == 2
    assert not create.called
    assert files(root)[name] == saved_bytes


@pytest.mark.parametrize('raw,expected', [
    ('not JSON', 'Failed to parse roadmap JSON'),
    ('{}', 'topic must be a string'),
    ('[]', 'Roadmap must be a JSON object'),
    (json.dumps(dict(CURRICULUM, phases=[])), 'phases must be a non-empty list'),
    (json.dumps(dict(CURRICULUM, target_level=[])), 'Roadmap validation failed'),
])
def test_invalid_output_is_saved_with_errors_without_retry(experiment, capsys, raw, expected):
    root, _constructor, create, response = experiment
    response.choices[0].message.content = raw
    before = files(root)
    assert cli.main(arguments(save='invalid.json')) == 1
    report = json.loads(capsys.readouterr().out)
    assert create.call_count == 1
    assert report['raw_response'] == raw
    assert any(expected in error for error in report['validation_errors'])
    assert report['roadmap'] is None
    after = files(root)
    assert json.loads(after.pop('experiments/roadmap_prompts/invalid.json')) == report
    assert after == before


def test_api_failure_is_reported_once_and_can_be_saved(experiment, capsys):
    root, constructor, create, _response = experiment
    create.side_effect = RuntimeError('Simulated API failure')
    assert cli.main(arguments(save='api-failure.json')) == 1
    report = json.loads(capsys.readouterr().out)
    assert create.call_count == 1
    constructor.assert_called_once_with(api_key='fake-test-key', max_retries=0)
    assert 'Simulated API failure' in report['error']
    assert report['raw_response'] is None and report['response_metadata']['usage'] is None
    assert report['prompt']['templates']
    assert json.loads((root / 'experiments/roadmap_prompts/api-failure.json').read_text()) == report


def test_usage_unavailable_is_explicit_without_fabricated_counts(experiment, capsys):
    _root, _constructor, create, response = experiment
    response.usage = None
    assert cli.main(arguments()) == 0
    assert create.call_count == 1
    assert json.loads(capsys.readouterr().out)['response_metadata']['usage'] is None


@pytest.mark.parametrize('overrides', [
    {'save': '../data/tasks.csv'}, {'save': '/tmp/report.json'}, {'save': 'subdir/report.json'},
    {'weekly_hours': '0.25'}, {'weekly_hours': 'nan'}, {'goal': '  '}, {'model': '  '},
    {'learning_purpose': 'interview_preparation'}, {'max_session_minutes': '22'},
])
def test_invalid_input_never_calls_model_or_changes_application_data(experiment, overrides):
    root, _constructor, create, _response = experiment
    before = files(root)
    with pytest.raises(SystemExit) as exc:
        cli.main(arguments(**overrides))
    assert exc.value.code == 2
    assert not create.called
    assert files(root) == before


def test_redirected_experiment_directory_is_rejected_before_request(experiment):
    root, _constructor, create, _response = experiment
    (root / 'experiments').symlink_to(root / 'data', target_is_directory=True)
    with pytest.raises(SystemExit) as exc:
        cli.main(arguments(save='report.json'))
    assert exc.value.code == 2
    assert not create.called
    assert not (root / 'data' / 'roadmap_prompts').exists()
