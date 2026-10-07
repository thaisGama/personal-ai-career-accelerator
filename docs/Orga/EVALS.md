# Evaluation Summary

| Eval           | Result  | Main Finding |
| -------------- | ------- | ------------ |
| New User       | NOT RUN |              |
| Returning User | NOT RUN |              |
| Failed Quiz    | NOT RUN |              |

---
# EVAL-001 — Fresh User

**Date:** 2026-06-17

---

# Goal

Validate system behavior for a new user with no existing learning state.

---

# Architecture Prediction

Expected flow:

```text
User Input
→ Planner Service
→ ReAct Controller
→ Memory Retrieval
→ Roadmap Generation
→ Task Summary
→ Weekly Plan Generation
→ Task Upsert
→ Save Outputs
→ Next Task Selection
```

---

# Observed Behavior

## Roadmap

Observed:

* New roadmap generated successfully.
* Roadmap files created:

  * `roadmaps/goal_learn_embeddings_for_rag_roadmap.json`
  * `roadmaps/goal_learn_embeddings_for_rag_roadmap.md`

## Tasks

Observed:

* Tasks were generated.
* Tasks appear under the new `roadmap_id`.
* Existing `tasks.csv` was not removed.

## Memory

Observed:

* New memory snippet appended.
* Existing memory history still visible.
* Older memory snippets remain accessible through the UI.

## Quiz

Observed:

* No quiz files generated.
* No quiz-related state changes detected.

---

# File Changes Observed

## Created

* `roadmaps/goal_learn_embeddings_for_rag_roadmap.json`
* `roadmaps/goal_learn_embeddings_for_rag_roadmap.md`
* `weekly_plans/week_2026-06-17_18-12-16-402359_plan.md`
* `posts/linkedin_week_2026-06-17_18-12-16-402359.md`
* `docs/learning_units/2026-06-17_18-12-16-402359_learning-unit-foundations-of-embeddings-for-rag.md`
* `data/traces/trace_2026-06-17_18-12-18.json`

## Modified

* `data/tasks.csv`
* `docs/memory.md`
* `data/memory_vectors.json`

---

# Comparison

| Component | Expected  | Actual    | Match |
| --------- | --------- | --------- | ----- |
| Roadmap   | Created   | Created   | ✅     |
| Tasks     | Created   | Created   | ✅     |
| Memory    | Updated   | Updated   | ✅     |
| Quiz      | No Change | No Change | ✅     |

---

# Unexpected Behavior

## Unexpected Behavior 1

### Scenario

Reset Scope = Everything

### Expected

* Existing tasks removed
* Clean learning state

### Observed

* `tasks.csv` still exists
* Previous tasks remain present

### Impact

Unclear whether previous tasks can influence future roadmap progress or planning.

---

## Unexpected Behavior 2

### Scenario

Reset Scope = Everything

### Expected

* Memory fully reset

### Observed

* Older memory snippets still visible in UI

### Impact

Unclear whether historical memory is still injected into planning or only displayed.

---

# Architecture Questions Raised

## Question 1

What does **Reset Scope = Everything** actually reset?

Current observation suggests:

* Roadmap reset → Yes
* Tasks reset → Unclear
* Memory reset → Unclear

Needs verification.

---

## Question 2

What exactly is shown in Memory Quick View?

Possibilities:

### A)

Tail of `memory.md`

### B)

Memory retrieved through semantic search and actually injected into the planner

Only option B affects planning behavior.

Needs verification.

---

# Findings

## Finding 1

Roadmap generation works successfully for a new goal.

## Finding 2

Task generation occurs even when an existing `tasks.csv` file is present.

## Finding 3

Memory persistence survives a full reset operation.

---

# Open Questions

* Are tasks isolated by `roadmap_id` during roadmap progress computation?
* Does historical memory influence roadmap generation after reset?
* Does historical memory influence weekly planning after reset?
* What state is actually deleted by Reset Scope = Everything?
* Does Memory Quick View represent stored memory or retrieved memory?

---

# Architecture Impact

No architecture assumptions disproven yet.

The following assumptions remain unverified:

* Tasks are isolated by `roadmap_id`.
* Historical memory does not influence roadmap generation after reset.
* Historical memory does not influence weekly planning after reset.
* Reset Scope = Everything truly resets all learning state.

Additional evaluations required before updating `architecture.md`.

# Follow-up Investigation

## Investigation 1 — Memory Influence

### Question

Does historical memory affect planning after a reset?

### Evidence

Trace output:

```json
"audit": {
  "memory_used": true,
  "memory_snippets_count": 4
}
```

Retrieved memory snippets:

* Focus on understanding RAG systems and their components.
* Practical application through micro-tasks.
* Emphasis on prompt crafting and chunking strategies.

All retrieved memories were directly related to the current goal.

### Conclusion

Memory is actively used during planning.

Memory is not merely displayed in the UI.

Relevant memories are retrieved through semantic search and injected into the planner prompt.

### Architecture Finding

The following architecture assumption is confirmed:

```text
Memory = qualitative context only
```

More precisely:

```text
Memory influences planning context.
Memory does not directly determine roadmap progress.
```

---

## Investigation 2 — Task Isolation

### Question

Do tasks from previous roadmaps affect roadmap progress?

### Evidence

Roadmap state after generation:

* Week number = 1
* Current phase = P1
* Current milestone = M1.1
* Completed hours = 0
* Remaining hours = 40

Despite older tasks existing in tasks.csv, the roadmap started from the beginning.

### Conclusion

Existing tasks from previous roadmaps did not advance roadmap progress.

Progress calculation appears isolated to the current roadmap.

### Architecture Finding

The following architecture assumption is currently supported:

```text
Tasks are scoped by roadmap_id for roadmap progression.
```

Additional evaluations are still required to fully confirm this behavior.

---

# Eval Status

Status: COMPLETE

Confidence Level: Medium

Reason:

Core architecture assumptions for roadmap creation, memory retrieval, task generation, and roadmap progression were validated.

Remaining uncertainty exists around the exact behavior of Reset Scope = Everything.


# EVAL-002 — Roadmap → Weekly Plan → Task → Quiz Alignment

## Goal

Determine whether roadmap milestones, generated weekly tasks, learning units, and quizzes remain aligned throughout the learning flow.

---

## Scenario

Roadmap generated for:

```text
Learn Embeddings for RAG
```

Current roadmap focus:

```text
P1 / M1.1
Foundations: LLM Mental Models and Prompt/Tool Fundamentals
```

Quiz generated using:

```text
Use tasks.csv = True
roadmap_id = goal_learn_embeddings_for_rag
```

---

## Evidence Collected

### Roadmap Milestone

Current milestone:

```text
M1.1
Foundations: LLM Mental Models and Prompt/Tool Fundamentals
```

---

### Generated Weekly Plan

Week 1 tasks:

```text
Day 1: Overview of RAG Systems
Day 2: Understanding RAG Pipelines
Day 3: Introduction to Embeddings
Day 4: Prompt Engineering Basics
Day 5: Practical Application of Concepts
```

---

### Selected Quiz Tasks

Quiz selected:

```text
Overview of RAG Systems
Understanding RAG Pipelines
Milestone: Foundations: LLM Mental Models and Prompt/Tool Fundamentals
```

---

### Learning Unit

Learning Unit content focused on:

* RAG systems
* Retrieval
* Generation
* Embeddings
* Similarity search
* Retrieval pipelines
* Prompt design using retrieved context

---

### Quiz Content

Quiz questions focused on:

* What RAG stands for
* Retrieval components
* RAG pipeline steps
* Embeddings
* Retrieval efficiency

---

## Findings

### Finding 1

Learning Unit and Quiz are strongly aligned.

The quiz directly tests concepts taught in the generated learning unit.

---

### Finding 2

Quiz generation appears task-driven.

Questions correspond closely to selected tasks:

```text
Overview of RAG Systems
Understanding RAG Pipelines
Introduction to Embeddings
```

---

### Finding 3

Roadmap milestone alignment remains unclear.

Roadmap milestone:

```text
M1.1
Foundations: LLM Mental Models and Prompt/Tool Fundamentals
```

Generated weekly content:

```text
RAG Systems
RAG Pipelines
Embeddings
```

The relationship between milestone objectives and generated weekly content is not yet fully understood.

---

## Architecture Questions Raised

### Question 1

What is the primary object being validated by the quiz?

Possible interpretations:

A)

```text
Weekly tasks
```

B)

```text
Roadmap milestones
```

C)

```text
Weekly tasks that contribute toward milestone completion
```

Current evidence supports C, but additional evaluation is required.

---

### Question 2

How are weekly tasks linked to roadmap milestones?

Observed:

* Milestone tasks contain phase_id and milestone_id.
* Generated weekly tasks do not contain phase_id or milestone_id.
* Weekly tasks and milestone tasks coexist in tasks.csv.

Relationship remains unclear.

---

### Question 3

What is the true source of truth for learning progress?

Current candidates:

* Milestone tasks
* Weekly tasks
* Combination of both

Further evaluation required.

---

## Architecture Impact

No architecture assumptions disproven.

However, the following area remains insufficiently understood:

```text
Roadmap
    ↓
Milestone
    ↓
Weekly Tasks
    ↓
Learning Unit
    ↓
Quiz
    ↓
Task Validation
    ↓
Roadmap Progress
```

Future evaluations should focus on understanding how milestone tasks and weekly tasks interact.

## Outcome

This evaluation exposed a terminology and modeling issue.

The system currently uses the term "task" for multiple concepts:

* Roadmap milestone progress
* Weekly study topics
* Learning activities
* Quiz validation targets

This ambiguity made it difficult to reason about progression, quiz generation, and roadmap alignment.

As a result, a redesign discussion was initiated before continuing further evaluations.

See:
DESIGN_DECISIONS.md

## Day-Centric Refactor Evals

## EVAL-003 — Fresh Day-Centric User

### Goal

Validate the complete flow for a new user under the new day-centric architecture.

### Initial State

- Empty memory
- Empty roadmaps
- Empty learning_progress.json
- Empty generated learning units
- Empty quizzes
- Empty weekly plans

### Input

Goal:
Learn LLM Tool Calling Basics

Time available per week (hours):
5

Max session length (minutes):
60

Use agent loop (multi-step) -> enabled

Preferences / constraints
Busy working mom. Prefer practical steps. Each task must fit in the max session time. Include deliverables and a LinkedIn draft.

Learning intensity:
medium

### Expected Behavior

1. Roadmap generated — yes
2. Weekly plan generated — yes
3. Plan uses Day 1, Day 2, etc. — yes (day-centric output)
4. `data/learning_progress.json` created — yes
5. Week object persisted in `learning_progress.json` — yes
6. Day objects persisted under `weeks[].days[]` — yes
7. No quiz generated yet — no `quiz_path` populated
8. No review days generated — all days have `is_review = false`
9. Every generated day has status=TODO -> yes
10. `tasks.csv` may exist for compatibility, but must not be treated as source of truth


# EVAL-004 — Day Learning Unit Generation

## Goal

Validate that a Learning Unit can be generated for a specific Day and linked back to that Day in `learning_progress.json`.

## Initial State

- EVAL-003 completed
- `data/learning_progress.json` exists
- At least one Week exists
- At least one Day exists with:
  - `status = TODO`
  - empty `learning_unit_path`
  - empty `quiz_path`

## Input

Selected Day:
`day_001`

Action:
Generate Learning Unit for selected Day.

## Expected Behavior

1. System loads `data/learning_progress.json`.
2. System finds `day_001`.
3. Learning Unit is generated for `day_001` topic.
4. Learning Unit is saved under `docs/learning_units/`.
5. `day_001.learning_unit_path` is updated.
6. Other Days remain unchanged.
7. No quiz is generated.
8. Day status remains `TODO`.
9. Week/Roadmap status remains unchanged.


# EVAL-004 — Learning Unit Alignment After Week Generation

## Goal

Validate how the automatically generated Learning Unit relates to the new Day-centric model.

## Expected

- Learning Unit generated
- Linked to Day
- Stored in learning_progress.json

## Observed

- Learning Unit generated automatically
- Covers the entire week
- Not linked to a specific Day

## Checks

1. Is a Learning Unit file generated? Yes
2. Is `learning_unit_path` stored anywhere in `learning_progress.json`? No, path is empty
3. Is it stored at Week level or Day level? At day level in `learning_progress.json`
4. Do individual Days have empty or populated `learning_unit_path`? empty
5. Does the content match the whole Week or one specific Day? The whole week (milestone/week related)

## Result

**Status:** PARTIAL

**Reason:**
The generated Learning Unit is week/milestone-level, not Day-level.
The current implementation does not yet satisfy the target Day → Learning Unit relationship from the day-centric architecture.

---

## EVAL-PR1-001 — Failed Generation, Retained Plan, and Successful Retry

**Date:** 2026-10-07

**Scope:** Revised PR 1 on `feature/planner-roadmap-selection`.

**Result:** PASS — automated verification; manual browser/provider verification not performed.

### Contract inspected

`run_weekly_planner_service` returns `result`, `plan_md`, and `linkedin_md`. It normalizes direct `plan_path` and ReAct `weekly_plan_path` to `result.plan_path`. Exceptions propagate to the UI. A supported ReAct failure is the `_safe_final_result` shape with an empty `weekly_plan_path` and `final_reason` such as `parse_error`; it need not contain an `error` key. The earlier synthetic `error`-only test did not verify this supported shape.

### Automated setup and observations

Streamlit 1.52.1 AppTest runs the current `app.py` with `BASE_DIR` redirected to pytest temporary directories. Initial successful generation is mocked; subsequent failure and retry use the real planner-service wrapper with mocked direct/ReAct backends. No paid API, live credentials, real study-file deletion, or progress reset is used.

Each failure scenario starts with a successfully saved `generated.md` selected and its plan/LinkedIn preview and result retained:

| Scenario | Automated observation | Result |
| --- | --- | --- |
| Backend raises `RuntimeError("Provider unavailable")` | Error includes provider failure; working selection, previews, result, and saved-plan bytes remain unchanged; no success message. Successful mocked retry selects the newly saved `retry.md` and displays its content. | PASS |
| ReAct returns supported failure result (`weekly_plan_path = ""`, `final_reason = "parse_error"`) | Real service returns no saved plan; UI displays an error including the failure reason, keeps the working plan/content, and announces no success. Successful ReAct-shaped mocked retry selects `retry.md`. | PASS |
| Backend reports a nonexistent generated file | UI displays missing-output error, retains the existing selection/content and previews, and never selects the nonexistent file. Successful mocked retry selects `retry.md`. | PASS |
| Previously selected file removed from temporary fixtures; another plan exists | UI warns that the previous selection is unavailable and displays the remaining saved plan. No generation is called. | PASS |
| Last remaining saved plan removed from temporary fixtures | UI shows “No weekly plans found”, renders without exception, and offers no nonexistent plan option. No generation is called. | PASS |
| Selected temporary roadmap removed; malformed JSON also present | Invalid selection is cleared and generation is disabled. No generation is called. | PASS |
| Truly empty temporary roadmap directory | Existing-roadmap route has no selected value, disables generation, and explains how to create a roadmap via a new goal. Switching to the new-goal route enables generation without calling it. Existing plan browsing still works. | PASS |

### Failure reproduced and scoped fix

Before the fix, the strengthened focused suite returned **3 failed, 5 passed**: all three failed-generation scenarios retained their working state correctly but still displayed the old unconditional “Saved” success message. The UI now announces “Saved” only on the run that successfully accepts a saved generated plan; subsequent browsing and failed attempts label retained output “Previously saved outputs”. Missing-plan service errors now include the supported `final_reason` and `trace_path` when present.

### Actual checks after the fix

- `.venv/bin/python -m pytest tests/test_planner_ui.py -q`: **8 passed**.
- `.venv/bin/python -m pytest -q`: **57 passed**.
- `.venv/bin/python -m compileall -q app.py tests/test_planner_ui.py`: passed.
- `git diff --check -- app.py tests/test_planner_ui.py docs/Orga/EVALS.md`: passed.
- Whole-worktree `git diff --check` reports a pre-existing extra blank line at EOF in unrelated `FOUNDER_NOTEBOOK.md`; that user edit is left untouched and excluded from this work package.

### Manual observations and unverified behavior

No new manual browser observations were made during this evaluation. AppTest verifies rendered elements, state, and fixture contents; it does not verify browser visual layout, real provider behavior, or rollback of backend writes if a real generation fails after partially saving artifacts. The mocked failures exercise no such partial writes. Trace-path guidance is implemented from the inspected contract but is not asserted in these tests.

### Follow-up findings — recorded only

1. **Roadmaps tab remains on an old roadmap after new-goal generation.** User-reported observation; code inspection shows independent `roadmaps_select` / `roadmaps_selected_path` browsing state and no post-generation synchronization to the newly generated roadmap. Current mock tests do not generate roadmap files, so they do not reproduce this exact manual flow. Discuss a deliberate post-generation browsing-selection update separately while preserving independence from planner inputs. No fix here.
2. **Narrow goals may produce excessively long curricula.** User-reported observation; no curriculum-length evaluation or live generation performed here. Evaluate goal-to-curriculum alignment, breadth, and duration in [provisional PR 5 — Generation policy and quality](REFACTOR_PLAN.md#provisional-pr-5--generation-policy-and-quality). No prompt or curriculum changes here.
