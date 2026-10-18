# Standalone roadmap prompt CLI (#28)

Test production roadmap prompts with one generation request, without running
Streamlit or the ReAct controller. The CLI never calls the roadmap persistence
tool, seeds tasks, constructs a memory store, updates progress, or generates
weekly plans, learning units, quizzes, or LinkedIn posts.

## Usage

From the repository root, with the project dependencies installed and
`OPENAI_API_KEY` set in the environment:

```bash
.venv/bin/python scripts/run_roadmap_prompt.py \
  --goal "Understand IAM identity policies and role trust policies" \
  --learning-purpose topic_mastery \
  --model gpt-6-luna \
  --weekly-hours 2 \
  --max-session-minutes 20 \
  --intensity medium \
  --background "Familiar with basic AWS services" \
  --preferences "Prefer practical scenarios" \
  --save iam-topic-v1.json
```

Running this command makes a model request. `--help` does not make one. No live or
paid requests were made during implementation or automated tests.

Required: `--goal`, `--learning-purpose`, `--model`.

Purpose values: `certification_preparation`, `topic_mastery`,
`career_development`. Interview Preparation is unsupported.

Optional settings reuse learner-setup validation:

- `--weekly-hours`: 0.5–10 in half-hour steps, default 2.
- `--max-session-minutes`: 10, 15, 20, 30, 45, or 60, default 30.
- `--intensity`: light, medium, or hardcore, default medium.
- `--background`, `--preferences`: strings, default empty.
- `--save NAME.json`: write a new report under the repository's
  `experiments/roadmap_prompts/`, which is ignored by Git. Only a simple filename
  is accepted; paths, existing filenames, and redirected experiment directories
  are rejected before the model request. Existing reports are never overwritten.

Without `--save`, the report is printed to stdout and no experiment file is
created. With `--save`, the same report is both printed and saved. Normal usage
logging goes to stderr so stdout remains valid JSON. The command works from
other working directories; saved reports still go under this repository.

The CLI uses the production client's temperature/token defaults and model
compatibility handling. It explicitly sets OpenAI SDK `max_retries=0`; both the
CLI and the SDK make no automatic retry. A valid, configured experiment attempts
one generation call. Invalid input, unavailable credentials, or an unusable save
path can fail before a network request. An API failure is reported without retry.

## Report

Each JSON report includes:

- `stage` (`roadmap`), UTC creation time, and complete input `learner_setup`.
- `requested_model` and `response_metadata`: returned model and prompt,
  completion, and total token usage. Unavailable model/usage data is `null`, not
  guessed or inferred from console text.
- `prompt.system`, `prompt.user`: the exact rendered production messages.
- `prompt.templates`: IDs, versions, and SHA-256 hashes for the selected roadmap
  system/user templates and both purpose templates used in composition.
- `raw_response`: exact generated text, including tags/formatting when present.
- `roadmap`: the parsed, validated roadmap with application-owned learner setup,
  or `null` on a parsing/validation failure. Raw invalid output is retained.
- `validation_errors` and `error`: schema, parse, or request diagnostics.

Exit status is 0 for a validated result, 1 for a request/parse/validation failure,
and 2 for argument or output-file errors. Failed generations can be saved for
comparison just like successful ones; no repair request is made.

## Reuse and limits

The application and CLI share `tools.build_roadmap_prompt` and
`tools.parse_roadmap_output`, extracted from the existing roadmap tool without
changing its prompt text, selection, parsing, validation, persistence, or seeding
behavior. The CLI calls `weekly_planner.call_llm` directly and opts into structured
response metadata and disabled retries; production callers retain their existing
return type, logging, and SDK retry defaults.

AI Engineering career goals select the original AI Engineer system template;
other careers, certification, and topic goals select the focused template.
No templates or prompt versions are changed by this feature. Preferences are
accepted and captured in learner setup; the current production roadmap messages
do not explicitly render that field, and this CLI deliberately preserves that
behavior rather than tuning prompts.

Validation is the existing production structural validation, not a quality judge
or certification-readiness check. Reports contain templates and inputs, but there
is no evaluation runner, scoring, model comparison engine, prompt override,
provider integration, or additional generation stage.

## Tests

```bash
.venv/bin/python -m pytest -q tests/test_roadmap_prompt_cli.py tests/test_llm_compatibility.py tests/test_prompt_snapshots.py tests/test_roadmap_learner_setup.py tests/test_learning_purpose.py
.venv/bin/python -m pytest -q
```

Tests mock the OpenAI boundary, check exactly one completion and disabled SDK
retries, compare requests with production rendering, check all purpose-selection
branches and template/usage metadata, exercise parsing/schema/request failures,
and verify experiment saves leave application files unchanged. Persistence,
embedding, and downstream-generation entry points are guarded against accidental
invocation.
