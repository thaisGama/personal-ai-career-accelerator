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
