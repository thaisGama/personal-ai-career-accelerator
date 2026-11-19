"""Shared output validation: no generation, repairs, or persistence on rejection."""
import copy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.agent import tools
from test_roadmap_learner_setup import CURRICULUM, SETUP
from test_standalone_roadmap import CURRICULUM as STANDALONE_CURRICULUM


def set_field(data, path, value):
    for key in path[:-1]:
        data = data[key]
    data[path[-1]] = value


FIELDS = [
    ('total_estimated_hours',),
    ('phases', 0, 'estimated_hours'),
    ('phases', 0, 'milestones', 0, 'estimated_hours'),
    *[('estimated_weeks_at_hours_per_week', key) for key in ('2', '5', '7')],
]


@pytest.mark.parametrize('fixture', [CURRICULUM, STANDALONE_CURRICULUM])
def test_existing_valid_fixtures(fixture):
    assert tools._validate_curriculum_schema(fixture) == (True, [])
    assert 'roadmap' in tools.parse_roadmap_output(json.dumps(fixture), SETUP)


@pytest.mark.parametrize('path', FIELDS)
@pytest.mark.parametrize('value', [-5, 0, True, False, float('nan'), float('inf'),
                                 -float('inf'), '5', None])
def test_invalid_estimate_rejected_at_shared_boundary(path, value):
    data = copy.deepcopy(CURRICULUM)
    set_field(data, path, value)
    assert not tools._validate_curriculum_schema(data)[0]
    assert 'error' in tools.parse_roadmap_output(json.dumps(data), SETUP)


@pytest.mark.parametrize('path', FIELDS[:3])
@pytest.mark.parametrize('difference,valid', [(0.05, True), (-0.05, True),
                                             (0.051, False), (-0.051, False), (994, False)])
def test_hour_sum_tolerance(path, difference, valid):
    data = copy.deepcopy(CURRICULUM)
    set_field(data, path, 5 + difference)
    # Use fractional weeks consistent with the changed total.
    data['estimated_weeks_at_hours_per_week'] = {
        key: data['total_estimated_hours'] / int(key) for key in ('2', '5', '7')}
    assert tools._validate_curriculum_schema(data)[0] is valid


@pytest.mark.parametrize('weeks,valid', [
    ({'2': 2.5, '5': 1, '7': 0.71}, True),
    ({'2': 3, '5': 1, '7': 1}, True),
    ({'2': 2.55, '5': 1, '7': 1}, True),
    ({'2': 2.45, '5': 1, '7': 1}, True),
    ({'2': 2.551, '5': 1, '7': 1}, False),
    ({'2': 2.449, '5': 1, '7': 1}, False),
    ({'2': 2, '5': 1, '7': 1}, False),
    ({'2': 3.01, '5': 1, '7': 1}, False),
    ({'2': 3, '5': 999, '7': 1}, False),
])
def test_fractional_or_ceiling_weeks(weeks, valid):
    assert tools._validate_curriculum_schema(dict(CURRICULUM,
        estimated_weeks_at_hours_per_week=weeks))[0] is valid


def test_multiple_phases_and_milestones_with_decimal_rounding():
    data = copy.deepcopy(CURRICULUM)
    phase = data['phases'][0]
    phase['estimated_hours'] = 0.3
    phase['milestones'] = [dict(phase['milestones'][0], estimated_hours=v)
                           for v in (0.1, 0.2)]
    data['phases'].append(copy.deepcopy(phase))
    data['total_estimated_hours'] = 0.6
    data['estimated_weeks_at_hours_per_week'] = {'2': 0.3, '5': 0.12, '7': 0.09}
    assert tools._validate_curriculum_schema(data) == (True, [])


def test_no_arbitrary_duration_ceiling():
    data = copy.deepcopy(CURRICULUM)
    for path in FIELDS[:3]:
        set_field(data, path, 70 * 10**10)
    data['estimated_weeks_at_hours_per_week'] = {
        key: 70 * 10**10 // int(key) for key in ('2', '5', '7')}
    assert tools._validate_curriculum_schema(data) == (True, [])


def test_original_generator_rejects_before_any_persistence(tmp_path, monkeypatch):
    data = copy.deepcopy(CURRICULUM)
    data['phases'][0]['milestones'][0]['estimated_hours'] = 999
    calls = []
    monkeypatch.setattr(tools, 'call_llm', lambda **kw: calls.append(kw) or json.dumps(data))
    result = tools.tool_generate_learning_roadmap(
        SETUP['goal'], 'medium', '', 'test', tmp_path, 'mock', SETUP)
    assert 'error' in result
    assert len(calls) == 1
    assert list(tmp_path.iterdir()) == []
