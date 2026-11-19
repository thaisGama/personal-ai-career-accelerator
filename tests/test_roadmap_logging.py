"""One sanitized terminal record per admitted attempt; logging is best effort."""
import json
import logging
from types import SimpleNamespace
from unittest.mock import Mock

import openai
import pytest

from standalone_roadmap import service
from test_standalone_roadmap import api, INPUTS, CURRICULUM


def outcomes(caplog):
    return [record.getMessage() for record in caplog.records
            if record.name == service.__name__]


@pytest.mark.parametrize('failure,category', [
    (None, 'none'), ('timeout', 'api_timeout'), ('api', 'api_failure'),
    ('output', 'invalid_output'), ('hours', 'invalid_output'),
])
def test_safe_terminal_outcome(api, monkeypatch, caplog, failure, category):
    _, create, response = api
    response.model = 'provider-model'
    response.usage = SimpleNamespace(prompt_tokens=100, completion_tokens=25, total_tokens=125)
    if failure == 'timeout':
        create.side_effect = openai.APITimeoutError(request=Mock())
    elif failure == 'api':
        create.side_effect = RuntimeError('PRIVATE_API_DIAGNOSTIC')
    elif failure == 'output':
        response.choices[0].message.content = 'PRIVATE_RAW_RESPONSE'
    elif failure == 'hours':
        response.choices[0].message.content = json.dumps(dict(CURRICULUM, total_estimated_hours=-5))
    ticks = iter([10.0, 11.25])
    monkeypatch.setattr(service, 'perf_counter', lambda: next(ticks))
    with caplog.at_level(logging.INFO, logger=service.__name__):
        inputs = dict(INPUTS, goal='PRIVATE_LEARNER_GOAL', background='PRIVATE_BACKGROUND')
        if failure:
            with pytest.raises(service.RoadmapGenerationError):
                service.generate_roadmap(**inputs)
        else:
            service.generate_roadmap(**inputs)
    records = outcomes(caplog)
    assert len(records) == 1
    message = records[0]
    assert f'outcome={"failure" if failure else "success"}' in message
    assert f'category={category}' in message
    assert 'duration_seconds=1.250' in message
    assert f'model={service.ROADMAP_MODEL}' in message
    assert f'input_tokens={None if failure in ("api", "timeout") else 100}' in message
    assert f'output_tokens={None if failure in ("api", "timeout") else 25}' in message
    assert 'PRIVATE_' not in caplog.text
    assert 'fake-server-key' not in caplog.text
    assert 'Return JSON' not in caplog.text
    create.assert_called_once()


@pytest.mark.parametrize('failure', [False, True])
def test_logging_failure_preserves_result_quota_and_capacity(api, monkeypatch, failure):
    _, create, response = api
    monkeypatch.setenv('ROADMAP_DAILY_LIMIT', '2')
    monkeypatch.setattr(service.logger, 'info', Mock(side_effect=RuntimeError('broken handler')))
    if failure:
        response.choices[0].message.content = 'invalid'
        with pytest.raises(service.RoadmapGenerationError):
            service.generate_roadmap(**INPUTS)
    else:
        assert service.generate_roadmap(**INPUTS)
    response.choices[0].message.content = json.dumps(CURRICULUM)
    assert service.generate_roadmap(**INPUTS)
    with pytest.raises(service.RoadmapUnavailableError, match='allowance'):
        service.generate_roadmap(**INPUTS)
    assert create.call_count == 2
    assert service.logger.info.call_count == 2


def test_refused_and_invalid_requests_have_no_generation_outcome(api, monkeypatch, caplog):
    with pytest.raises(ValueError):
        service.generate_roadmap(**dict(INPUTS, goal=' '))
    monkeypatch.setenv('ROADMAP_GENERATION_ENABLED', 'false')
    with pytest.raises(service.RoadmapUnavailableError):
        service.generate_roadmap(**INPUTS)
    assert outcomes(caplog) == []
    api[1].assert_not_called()


def test_unexpected_token_metadata_cannot_expose_text(api, caplog, capsys):
    _, create, response = api
    response.model = 'PRIVATE_PROVIDER_TEXT'
    response.usage = SimpleNamespace(prompt_tokens='PRIVATE_TOKEN_TEXT',
                                    completion_tokens=True, total_tokens=999)
    assert service.generate_roadmap(**INPUTS)
    assert len(outcomes(caplog)) == 1
    assert 'input_tokens=None output_tokens=None' in outcomes(caplog)[0]
    assert 'PRIVATE_' not in caplog.text
    assert 'PRIVATE_' not in capsys.readouterr().out
    create.assert_called_once()
