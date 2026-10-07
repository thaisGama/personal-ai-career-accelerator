# REFACTOR_PLAN — Day-Centric Learning Architecture

**Status:** Draft
**Purpose:** Migrate the current task-based learning system to the planned day-centric progression architecture.

---

# Goal

Refactor the learning system from:

```text
Roadmap
→ Weekly Plan
→ Tasks
→ Quiz
→ Task Validation
```

to:

```text
Roadmap
→ Phase
→ Milestone
→ Week
→ Day
→ Learning Unit
→ Quiz
→ PASS / FAIL
```

The new source of truth for progression will be:

```text
data/learning_progress.json
```

---

# Non-Goals

This refactor does **not** aim to:

* Build a full educational analytics platform.
* Add numerical progress scoring.
* Add question-level mastery tracking.
* Redesign the whole Streamlit UI.
* Replace memory search.
* Optimize prompts deeply.

The goal is to make progression understandable, testable, and aligned with the target architecture.

---

# Target Concepts

## Day

The smallest unit of learning and progression.

A Day contains:

* Topic
* Learning Unit
* Quiz
* PASS / FAIL validation
* Status

## Week

A milestone execution slice.

A Week contains Days.

Week status is computed from Day status.

## Milestone

A curriculum objective.

Milestone status is computed from Week status.

## Memory

Memory is used for personalization and review generation only.

Memory does not determine progression.

---

# Refactor Roadmap

## Sprint 1 — Rename Tasks to Days in Planner Output

### Goal

Stop using "Task" to describe daily learning topics.

### Current Behavior

Weekly plan generates:

```text
🔥 Task 1 (20 min): Overview of RAG Systems
```

### Target Behavior

Weekly plan generates:

```text
🔥 Day 1 (20 min): Overview of RAG Systems
```

### Scope

Update planner prompts and parsing logic so the generated plan contains Days instead of Tasks.

### Files likely affected

* `weekly_planner.py`
* `task_store.py`
* `tools.py`
* `app.py`

### Acceptance Criteria

* Weekly plan displays Day 1, Day 2, etc.
* No new learning output refers to these as Tasks.
* Existing old task files do not need migration yet.

---

## Sprint 2 — Introduce `learning_progress.json`

### Goal

Create the new source of truth for learning progression.

### Target File

```text
data/learning_progress.json
```

### Minimal Structure

```json
{
  "roadmap_id": "goal_learn_embeddings_for_rag",
  "status": "TODO",
  "weeks": [
    {
      "week_id": "week_001",
      "phase_id": "P1",
      "milestone_id": "M1.1",
      "week_number_global": 1,
      "week_number_in_milestone": 1,
      "title": "Foundations of LLM Mental Models",
      "goal": "Understand basic LLM behavior and prompt/tool fundamentals.",
      "status": "TODO",
      "days": [
        {
          "day_id": "day_001",
          "day_number": 1,
          "topic": "What is an LLM?",
          "estimated_minutes": 20,
          "learning_unit_path": "",
          "quiz_path": "",
          "status": "TODO",
          "quiz_result": "",
          "completed_at": "",
          "reflection": "",
          "review_reason": "",
          "is_review": false,
          "review_of_day_id": ""
        }
      ]
    }
  ]
}
```

### Acceptance Criteria

* System can create `learning_progress.json`.
* System can load existing progress.
* System can append a generated Week with Days.
* `tasks.csv` is no longer required for new progression.

---

## Sprint 3 — Generate Weeks with Days

### Goal

Weekly generation should create a Week object with Day objects.

### Current Behavior

Weekly planner generates Markdown and extracts Tasks.

### Target Behavior

Weekly planner generates:

* Week metadata
* Day list
* Learning plan Markdown

Each Day should include:

* `day_id`
* `day_number`
* `topic`
* `estimated_minutes`
* `status = TODO`
* `phase_id`
* `milestone_id`
* `roadmap_id`

### Acceptance Criteria

* A generated week is stored in `learning_progress.json`.
* Each Day belongs to exactly one Week.
* Each Week belongs to exactly one Milestone.
* No standalone task objects are required.

---

## Sprint 4 — Generate Learning Unit Per Day

### Goal

Learning content should be generated for a specific Day, not for the whole week.

### Current Behavior

A single learning unit is generated for the week.

### Target Behavior

Each Day can generate or display its own Learning Unit.

Example:

```text
Day 1
→ Generate Learning Unit
→ docs/learning_units/day_001_*.md
```

### Inputs

* Day topic
* Milestone context
* Relevant memory
* Prior quiz feedback if review day

### Acceptance Criteria

* Each Day can have a `learning_unit_path`.
* Learning Unit content matches the Day topic.
* Learning Unit generation does not regenerate the full Week.

---

## Sprint 5 — Generate Quiz Per Day

### Goal

Quiz validates the Day's Learning Unit.

### Current Behavior

Quiz generation uses selected tasks.

### Target Behavior

Quiz generation uses:

* Day topic
* Day Learning Unit
* Milestone context

### Acceptance Criteria

* Quiz is linked to `day_id`.
* Quiz is saved to `docs/quizzes/`.
* Day stores `quiz_path`.
* Quiz questions match the Day Learning Unit.

---

## Sprint 6 — Implement PASS / FAIL Day Validation

### Goal

Quiz result updates Day status.

### Target Rules

```text
Quiz PASS
→ Day status = PASSED

Quiz FAIL
→ Day status = NEEDS_REVIEW
```

### Acceptance Criteria

* User submits quiz answers.
* System evaluates quiz.
* System stores `quiz_result`.
* System updates Day status.
* Numerical score may be stored as feedback, but does not drive progression.

---

## Sprint 7 — Compute Progression Upward

### Goal

Compute Week, Milestone, Phase, and Roadmap status from Day status.

### Rules

```text
All Days PASSED
→ Week PASSED

All Weeks PASSED
→ Milestone PASSED

All Milestones PASSED
→ Phase PASSED

All Phases PASSED
→ Roadmap PASSED
```

### Acceptance Criteria

* Week status is computed from Days.
* Milestone status is computed from Weeks.
* Progression does not depend on memory.
* Progression does not depend on `tasks.csv`.

---

## Sprint 8 — Implement Review Day Generation

### Goal

Support failed Days without regenerating the full Week.

### Flow

```text
Day Quiz FAIL
→ Day = NEEDS_REVIEW
→ User clicks "Generate Review Day"
→ System appends Review Day to same Week
```

### Review Day fields

```text
is_review = true
review_of_day_id = <failed_day_id>
```

### Inputs to Review Generation

* Failed Day topic
* Original Learning Unit
* Quiz feedback
* Relevant memory context

### Outputs

* Review Learning Unit
* Review Quiz
* New Review Day in `learning_progress.json`

### Acceptance Criteria

* System generates only one Review Day.
* System does not regenerate the Roadmap.
* System does not regenerate the Week.
* System does not modify completed Days.
* Review Day must pass before Week can pass.

---

# Migration Strategy

No full historical migration required for V1.

Existing files may remain:

* `tasks.csv`
* old weekly plans
* old quizzes
* old learning units

New day-centric progression starts from a clean or newly generated roadmap/week.

---

# Evaluation Plan After Refactor

## EVAL-003 — Week Generates Days

Validate:

```text
Roadmap
→ Week
→ Days
```

Expected:

* Week belongs to one Milestone.
* Days belong to one Week.
* Days stored in `learning_progress.json`.

---

## EVAL-004 — Day PASS Flow

Validate:

```text
Day
→ Learning Unit
→ Quiz
→ PASS
→ Day PASSED
```

Expected:

* Day status becomes PASSED.
* Week status updates if all Days are PASSED.

---

## EVAL-005 — Day FAIL and Review Flow

Validate:

```text
Day
→ Quiz FAIL
→ NEEDS_REVIEW
→ Generate Review Day
```

Expected:

* Original Day remains NEEDS_REVIEW.
* Review Day is appended.
* No full Week regeneration occurs.

---

## EVAL-006 — Week Completion

Validate:

```text
All Days PASSED
→ Week PASSED
```

Expected:

* Week status is computed.
* No manual Week status update required.

---

## EVAL-007 — Memory Adaptation

Validate:

```text
Memory
→ affects review content
→ does not affect progression
```

Expected:

* Review content reflects memory context.
* PASS / FAIL remains the only progression mechanism.

---

# Open Implementation Questions

* Should Day Learning Units be generated immediately with the Week, or lazily when the user opens the Day?
* Should Day Quizzes be generated immediately after the Learning Unit, or only when the user clicks "Generate Quiz"?
* Should `learning_progress.json` support multiple roadmaps or one active roadmap per file?
* Should Week generation be blocked if the current Week is not PASSED?

---

# Recommended First Implementation Step

Start with Sprint 1.

Reason:

It is the smallest visible change and aligns the UI language with the new architecture.

Do not implement review flow first.

First make the system speak the correct language:

```text
Task
→ Day
```

# Sprint Audit and Follow-up PRs — 2026-10-05

This audit checks the current repository rather than treating the sprint descriptions as completion claims. The original sprint goals and acceptance criteria above remain unchanged. Implementation, integration, and validation are recorded separately. No attached audit snapshot was available in this checkout; evidence below comes from code, tests, and the recorded evaluations in [EVALS.md](EVALS.md).

| Sprint | Implementation status | Integration status | Validation status | Remaining gap / follow-up |
| --- | --- | --- | --- | --- |
| 1 — Days in planner output | Day prompts and parsing implemented; legacy task compatibility remains. | Both planner modes append day-centric progress, but tasks still participate in orchestration and quiz UI. | Parser tests and EVAL-003 cover Day output; live LLM wording is not guaranteed by deterministic tests. | [PR 3](#provisional-pr-3--day-learning-and-quiz-ui) for day-centric interaction; [PR 5](#provisional-pr-5--generation-policy-and-quality) for output policy. |
| 2 — Progress store | Create/load/append implemented in `learning_progress_store.py`. | Both generation paths persist progress; `tasks.csv` remains part of planning and quiz flows. | Persistence tests; EVAL-003 records stored Weeks/Days. | [PR 4](#provisional-pr-4--progression-integration) for source-of-truth integration. |
| 3 — Weeks with Days | Week/Day extraction and ownership metadata implemented. | Wired into direct planner and ReAct save outputs; legacy tasks still written. | Week parsing/ownership tests; EVAL-003 records generated Days. | [PR 4](#provisional-pr-4--progression-integration) for task-independent progression/planning. |
| 4 — Learning Unit per Day | `tool_generate_learning_unit_for_day` saves and links a Day artifact. | Planner still eagerly generates a whole-week unit; UI lacks Day learning-unit action. | Focused tool test passes; recorded learning-unit alignment evaluation is PARTIAL. | [deferred Day-content proposal](#deferred-proposal--day-content-ownership-and-lazy-generation) and [PR 3](#provisional-pr-3--day-learning-and-quiz-ui). |
| 5 — Quiz per Day | Day quiz tool saves and links quiz using the Day unit. | Learning Check UI still uses topic/task quiz service. | Day quiz tool tests; live Day quiz UI flow not validated. | [PR 3](#provisional-pr-3--day-learning-and-quiz-ui). |
| 6 — PASS / FAIL validation | Day evaluation tool updates progress with PASS/FAIL. | UI evaluation still updates legacy tasks rather than invoking Day evaluation. | Day evaluation/store regression tests; live integrated Day submission unverified. | [PR 3](#provisional-pr-3--day-learning-and-quiz-ui). |
| 7 — Upward progression | Store recomputes Week/Milestone/Phase/Roadmap status from stored children. | Roadmap planning still computes focus using tasks; aggregation only knows generated children, not the entire curriculum. | Store aggregation tests; full UI completion flow unverified. | [PR 4](#provisional-pr-4--progression-integration). |
| 8 — Review Days | Tool appends a review Day without regenerating Week/Roadmap; artifact paths start empty. | No UI review action; review content/quiz must be generated separately. Original failed Day remains NEEDS_REVIEW, so passing its review alone does not clear Week status. | Review append/store tests; no end-to-end fail → review → completion validation. | [deferred Day-content proposal](#deferred-proposal--day-content-ownership-and-lazy-generation), [PR 3](#provisional-pr-3--day-learning-and-quiz-ui), and [PR 4](#provisional-pr-4--progression-integration). |

## Revised PR 1 — Planner entry and generated-plan selection

**Scope approved for implementation:** one entry point in planner inputs offers “Start a new learning goal” / “Use an existing roadmap”. Saved roadmap dropdown shows readable titles with stable loader-compatible identifiers. Setup inputs remain available; reuse does not restore prior settings or resume lessons. Empty/unavailable selections block generation with guidance. Roadmaps tab remains browse-only and loses its activation button. Explicit generation selects the exact saved weekly plan from the inspected service contract (`result.plan_path`), while older plans remain selectable. Errors preserve the previous working preview and selection; missing selected plans are handled gracefully.

**Acceptance criteria:** both routes work without widget-state errors; selected ID reaches generation; browsing is independent; new-goal route ignores old active/selected roadmap state; generation selects its returned saved plan; historical plans and later tabs remain usable; selection alone makes no generation calls or content writes.

**Implementation status:** implemented in `app.py`, with focused regression coverage in `tests/test_planner_ui.py`.

**Integration status:** uses the existing planner service unchanged. Its normalized `result.plan_path` covers direct (`plan_path`) and ReAct (`weekly_plan_path`) backends. IDs remove the `_roadmap.json` suffix expected by the loader. A new goal passes no explicit ID; the backend intentionally retains goal-derived roadmap reuse when a saved roadmap matches the goal, plus the existing explicit force-regeneration option. Old activation state is no longer consulted.

**Validation status:** Streamlit AppTest checks routing, independent browsing, exact returned plan despite another file's newer mtime, historical selection, errors/no path/missing generated file, removed files, empty roadmaps, and later-tab rendering. Service tests check ID forwarding and normalized result paths for both modes. Validation command: `.venv/bin/python -m pytest -q` (56 passed, including 7 new cases); `git diff --check` and Python compilation also pass. No additional required check configuration or CI workflow exists in this checkout. Live provider generation and browser visual rendering are not verified by these tests.

**Out of scope:** restoring settings; lesson resumption; preventing unnecessary generation; curriculum/prompt changes; critic repair; diagnostics; daily quiz integration; broader UI redesign. Only this PR is implemented. Follow-up proposals below are discussion placeholders, not approved implementation scopes or revised sprint acceptance criteria.

## Agreed PR 2 — Embedded learner setup and read-only restoration

This agreed scope replaces the former provisional PR 2 numbering; the Day-content idea remains deferred below. PR 1 is merged. Its original scope/status above records that delivery, not the extensions authorized here.

**Goal:** save each roadmap’s submitted learner setup in its JSON and restore it as read-only when selected, with a fresh start and no legacy support.

**Scope:** application-owned `learner_setup` includes `goal`, `background`, `preferences`, `hours_per_week`, `max_session_minutes`, and `learning_intensity`. Validate model curriculum separately, attach exact submitted setup deterministically, validate the complete roadmap, and persist JSON plus its readable Markdown rendering through the shared roadmap-generation tool. Both direct and ReAct generation paths must provide the same metadata. Intentionally empty optional strings are valid.

Existing-roadmap selection loads JSON, restores and locks the six fields, and uses separate widget keys from the editable new-goal draft. The service reloads saved metadata before generation so stale inputs cannot override it. Existing-roadmap force regeneration is disabled to preserve settings, curriculum, and identity. Selecting/rerunning does not generate or modify files/progress. Invalid/missing metadata errors block generation; persistence failures must surface without announcing success.

**Fresh start:** user authorized removal of obsolete generated JSON/Markdown only from the application’s `roadmaps/` directory after backing up study files. Eight obsolete artifacts (four pairs) without setup were removed locally. They were ignored/untracked, so deletion does not appear as tracked file removal in this PR. Backups, other study artifacts, fixtures, source, and documentation are preserved. No migration, missing-setup defaults for saved roadmaps, or historical setup form is added.

**Acceptance criteria:** exact submitted values persist in both generation routes; a fresh app session restores from disk; saved fields are disabled; switching A/B keeps settings separate; generation receives persisted settings; switching back restores editable new-goal inputs without another roadmap’s ID; empty optional fields work; invalid/incomplete metadata blocks generation with an error; selection/reruns preserve artifacts/progress; failed saves do not announce success; relevant PR 1 regressions pass.

**Implementation/integration status:** implemented in shared roadmap validation/render/save, direct/ReAct input forwarding, planner service, and Streamlit input routing. Original sprint goals and acceptance criteria remain unchanged.

**Validation status:** automated persistence and Streamlit AppTest coverage recorded in [EVAL-PR2-001](EVALS.md#eval-pr2-001--embedded-setup-and-read-only-restoration). No paid APIs used. Manual restart/browser verification remains pending.

**Out of scope:** editing existing settings, legacy migration/compatibility, daily resume, lesson selection, curriculum policy, critic repair, roadmap-tab synchronization, general redesign, and resetting other learning data. Remaining PR scopes stay provisional.

## Deferred proposal — Day content ownership and lazy generation

Discuss replacing eager week-level content with Day-owned content, including review inputs and when artifacts should be generated. Linked gaps: Sprints 4 and 8. Former provisional PR 2; not implemented in the agreed learner-setup PR 2.

## Provisional PR 3 — Day learning and quiz UI

Discuss selecting a Day and connecting its unit, quiz, evaluation, and review actions to the existing Day tools. Linked gaps: Sprints 1, 4, 5, 6, and 8. No implementation in PR 1.

## Provisional PR 4 — Progression integration

Discuss making Day status the planning/UI source of truth, curriculum-aware completion, and resolution of failed Days through passed reviews. Linked gaps: Sprints 2, 3, 7, and 8. No implementation in PR 1.

## Provisional PR 5 — Generation policy and quality

Discuss unnecessary generation, prompt/curriculum policy, critic repair, diagnostics, and the guardrail/tool-boundary notes below. Linked gap: Sprint 1 wording policy and existing backlog notes. No implementation in PR 1.

---

# NEXT FIXES TO PLAN:
## Refactor guardrails, probably exclude all those guardrails midcode!! Instead use guardrail function next_required tasks, also review actually needed guardrails.
## clean up tool code:
Yes, that confusion is reasonable. You are not missing something.

The issue is that `generate_weekly_plan` is a **tool wrapper**, but it delegates the actual LLM work to `generate_weekly_plan_and_learning_unit()` in `weekly_planner.py`. So when you search inside `tools.py`, it looks like `tool_generate_weekly_plan()` does not call the LLM, even though behaviorally that tool absolutely triggers LLM calls.

Current shape:

```text
ReAct controller
  -> tool_generate_weekly_plan()
       -> generate_weekly_plan_and_learning_unit()
            -> call_llm()  # weekly plan
            -> call_llm()  # learning unit
            -> call_llm()  # optional retry
```

So the code is not wrong, but the boundaries are muddy.

A cleaner design would make this easier to reason about:

```text
tools.py
  tool_generate_learning_roadmap()
  tool_generate_weekly_plan()
  tool_generate_learning_unit()
  tool_run_plan_critic()

llm_gateway.py
  call_llm()

weekly_planner.py
  prompt builders
  parsers
  formatting
  deterministic helpers
```

Or, at minimum, rename/split the delegated function:

```text
tool_generate_weekly_plan()
  -> generate_weekly_plan_content_with_llm()
  -> generate_week_learning_unit_with_llm()
```

The main smell is that `weekly_planner.py` currently mixes several responsibilities:

- prompt construction
- actual OpenAI calls
- parsing/formatting
- high-level orchestration
- persistence/saving
- some roadmap loading/generation logic

That makes “where are the LLM calls?” harder to answer than it should be.

For the ReAct path, I’d probably refactor toward one of these rules:

- every ReAct tool that triggers an LLM should call an obvious `*_with_llm()` function directly, or
- all LLM calls should live in one module, and tools should call named generation services from there.

So your instinct is sound: searching `call_llm` technically finds the calls, but it does not clearly reveal the **tool-level behavior** because one tool hides its LLM calls behind a broad helper.