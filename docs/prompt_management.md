# Prompt management

Production text-generation prompts live in `src/agent/prompts/templates/`. The
small loader uses UTF-8 files and Python named formatting; there is no registry
service, prompt framework, evaluation runner, or reporting dependency. This is
PR 2 (#18), independent of the deferred PR 1 evaluation baseline.

PR 3 adds purpose-aware composition and five new template IDs; see
[Learning Purpose MVP](learning_purpose.md) for selection, propagation, and
legacy behavior. All original PR 2 template files remain unchanged.

## Production inventory

Inventoried against `5f399f0` before extraction. IDs below map to paths by replacing
`.` with `/` and appending `.txt`. All extracted templates start at `1.0.0` in
`src/agent/prompts/versions.json`.

| Entry point | Template IDs | Status |
| --- | --- | --- |
| `weekly_planner.build_weekly_planner_prompt` (direct and agent plans) | `weekly_plan.system`, `weekly_plan.user`, `weekly_plan.task_progress` | Extracted |
| `weekly_planner.generate_and_save_week`, `tools.tool_generate_weekly_plan` | `weekly_plan.no_memory` | Extracted shared first-week fallback |
| `weekly_planner.build_learning_unit_prompt` (weekly and day units) | `learning_unit.system`, `learning_unit.user` | Extracted |
| `weekly_planner.generate_weekly_plan_and_learning_unit` | `learning_unit.plan_excerpt`, `learning_unit.weekly_repair` | Extracted; weekly repair remains distinct from day repair |
| `tools.tool_generate_learning_roadmap` (direct and agent routes) | `roadmap.system`, `roadmap.user` | Extracted |
| `learning_check.generate_micro_quiz` | `quiz.system`, `quiz.user`, `quiz.task_focus` | Extracted; public system-prompt constant retained |
| `learning_check.evaluate_micro_quiz` (also used by day grading) | `quiz_evaluation.system`, `quiz_evaluation.user` | Extracted; public system-prompt constant retained |
| `react_agent.build_react_controller_prompt` | `controller.system`, `controller.user`, `controller.tools` | Extracted |
| `react_agent.run_weekly_planner_agent_react` invalid-JSON retry | `controller.json_repair_system`, `controller.json_repair_user` | Extracted |
| `critic.run_plan_critic` | `critic.system`, `critic.user` | Extracted |
| `tools.tool_generate_learning_unit_for_day` (normal and review days) | `day_learning_unit.roadmap_context`, `day_learning_unit.plan_context`, `day_learning_unit.review_context`, `learning_unit.day_repair` | Extracted; reuses learning-unit system/user templates |
| `tools.tool_generate_quiz_for_day` | `day_quiz.context`, `day_quiz.user`, shared `quiz.system` | Extracted |
| Day quiz services / `tools.tool_evaluate_quiz_for_day` | Shared `quiz_evaluation.system`, `quiz_evaluation.user` | No separate prompt; delegate to existing evaluator |

No top-level system/user or retry prompt was unsafe to extract or deferred.

Runtime context composition stays in Python: memory retrieval and score/list
formatting, task rows, roadmap milestone selection and optional context/progress
rows (`tools._format_roadmap_context`, `_format_roadmap_progress`), learning-unit
fallback labels, truncation, joins, and conditional section inclusion. Extraction
of these data-formatting helpers is deferred: they are coupled to application
selection logic, `.strip()` behavior, and optional fields. In particular, the
existing final priority sentence in `_format_roadmap_context` remains there
unchanged. Their output is passed as template variables, not reinterpreted as
format syntax. Prompt-template versions do not version these helpers; a future
evaluation should also record the application revision and runtime inputs.

The critic's `docs/misbehaviors.md`, saved plans, learning material, learner data,
and retrieved memory remain runtime inputs. Embedding search queries are not
text-generation instruction templates and were not changed.

## Extraction risks and safeguards

- Preserve every leading/trailing newline, blank line, Unicode character, and
  Markdown hard-break space. Several templates intentionally have **no final
  newline**; do not let an editor add one automatically.
- Templates use `{name}` placeholders. Literal braces, especially in controller
  actions and roadmap JSON examples, are escaped as `{{` and `}}`. Runtime values
  containing braces or dollar signs are substituted once and never parsed again.
- Defaults, trimming, numeric/boolean conversion, task limits, context truncation,
  and section ordering stay at the existing call sites. The loader never strips,
  dedents, includes other files, or evaluates Python expressions.
- The two learning-unit repair instructions differ and have separate IDs. The
  controller retry also intentionally replaces its initial system/user messages.
- The quiz system-prompt constants remain available to existing callers. Restart
  the app after editing templates, since those constants load at module import.

No Learning Purpose was added. Curriculum, time budgets, learning-unit rules,
model parameters, UI, traces, and generated-content handling were not tuned.

## Rendering and metadata

```python
from src.agent.prompts import render_prompt, get_prompt_metadata, list_prompt_metadata

text = render_prompt("roadmap.user", goal="Learn RAG", target_level="medium", background="none")
metadata = get_prompt_metadata("roadmap.user")
# {"prompt_id": "roadmap.user", "version": "1.0.0", "sha256": "..."}
all_templates = list_prompt_metadata()  # deterministic, sorted by ID
```

The hash identifies the raw template bytes, before substitution, including brace
escaping and whitespace. Metadata is JSON serializable. Future evaluation callers
can explicitly select the relevant IDs from the inventory and record their
metadata. A composed request needs metadata for its system/user templates and any
context, tools, or repair templates used. No evaluation reporting or automatic
trace changes are implemented here.

## Editing and versions

1. Keep the ID stable for the same purpose. Add a new ID for a distinct variant;
   register its version and file together. Do not rename IDs just to reorganize code.
2. Bump the corresponding version for any template-byte change, including
   whitespace. Use patch for corrections, minor for compatible instruction
   additions, major for output/placeholder contract changes. Git retains old
   versions; this loader serves the checked-out revision only.
3. Review rendered diffs and update the template metadata fixture explicitly.
   For an intentional prompt change, review and update affected golden cases in
   that separate change; never regenerate the baseline to hide refactor failures.
4. If runtime composition changes the model-visible prompt, review the same
   snapshots and document the application change even if template hashes do not
   change.

## Regression evidence

`tests/fixtures/prompts/production_requests.json` was captured from the original
production builders and mocked LLM calls at `5f399f0` **before extraction**.
PR 3 intentionally updates the two roadmap snapshots for purpose-aware selection;
the other 18 scenarios retain their original text.
`tests/test_prompt_snapshots.py` compares 20 scenarios covering populated/empty
context, task focus, custom role, roadmap schema, controller state and JSON repair,
critic registry present/absent, weekly generation and quality repair, day units,
review units, and day quizzes with/without saved material. Comparisons do not
normalize prompt text or whitespace; request model/token/temperature options are
also retained where calls are captured.

`tests/test_prompt_loader.py` checks stable metadata, registry completeness,
working-directory independence, single-pass interpolation, missing values,
unknown IDs, and first-week memory behavior. All new tests use mocked LLM and
embedding boundaries.

```bash
.venv/bin/python -m pytest -q tests/test_prompt_loader.py tests/test_prompt_snapshots.py
.venv/bin/python -m pytest -q
```
