# Open Design Questions

## D-001

Question

Should memory influence planning if it conflicts with task state?

Current behavior

Both memory and tasks are injected into the planner prompt.

Problem

Memory may suggest repeating content while tasks indicate mastery.

Possible options

Option A
Tasks are source of truth.

Option B
Memory and tasks both influence planning.

Option C
Memory only influences presentation style.

Status

Open

## D-002

Question

How should learning failures influence future plans?

Current behavior

Quiz results update task evidence and validation.

Memory stores only weekly summaries.

Limitation

The system does not capture:

- teaching style used
- misconceptions
- learner feedback
- explanations that worked
- explanations that failed

Because of this, future plans cannot adapt pedagogical style.

Potential future direction

Introduce Learning Insights:

- misconception detected
- preferred explanation style
- common mistakes
- successful learning patterns

Planner could use these insights when generating future weeks.

Status

Open
Priority: Low
Reason: Current focus is documenting existing architecture.

## DD-003 — Day-Centric Learning Model

Date: 2026-06-23

### Problem

Problem was identified in eval 002
The term "task" is currently overloaded and used for multiple concepts:

* Roadmap milestone tracking
* Weekly study topics
* Learning activities
* Quiz validation targets

This creates ambiguity when reasoning about learning progress and quiz behavior.

---

### Decision

The primary execution unit will be a Day.

Instead of:

Task 1
Task 2
Task 3

the system will use:

Day 1
Day 2
Day 3

---

### New Mental Model

Roadmap
→ Week
→ Day
→ Learning Unit
→ Quiz
→ Validation

---

### Day Structure

Each day contains:

* Topic
* Learning content
* Quiz
* Validation result

Example:

Day 1
Topic: Overview of RAG Systems

Learning Unit:

* Concepts
* Examples
* Resources

Quiz:

* Multiple choice questions
* Open-ended questions
* Explain in your own words

Result:
PASS / FAIL

---

## DD-002 — Remove Artificial Distinction Between Tasks and Quiz Questions

### Problem

Current system treats:

* Tasks
* Quiz questions

as separate concepts.

In practice both are learning validation activities.

---

### Decision

Validation activities will be represented as quiz questions.

Examples:

* Explain RAG in your own words
* Draw a RAG pipeline
* Summarize embeddings

These are question types rather than separate task entities.

---

## DD-003 — Pass/Fail Validation (V1)

### Decision

Initial implementation will use:

PASS
FAIL

only.

---

### Rationale

The goal is validating progression, not educational analytics.

Simpler state model:

TODO
PASSED
FAILED

---

### Future Evolution

Potential future additions:

* Numerical score
* Mastery levels
* Question-level tracking

These are explicitly deferred.

---

## DD-004 — Hierarchical Learning Progression

Status: Accepted

Structure:

Roadmap
→ Phase
→ Milestone
→ Week
→ Day
→ Learning Unit
→ Quiz

**Cardinality**
1 Roadmap
→ many Phases

1 Phase
→ many Milestones

1 Milestone
→ many Weeks

1 Week
→ many Days

1 Day
→ 1 Learning Unit

1 Day
→ 1 Quiz

Roadmap
 └─ Phase
     └─ Milestone
         ├─ Week 1
         │   ├─ Day 1
         │   ├─ Day 2
         │   ├─ Day 3
         │   ├─ Day 4
         │   └─ Day 5
         │
         ├─ Week 2
         │   ├─ Day 1
         │   ├─ Day 2
         │   └─ ...
         │
         └─ Week N

**Progression model**

Day PASSED
→ contributes to Week completion

All Days PASSED
→ Week PASSED

All Weeks PASSED
→ Milestone PASSED

All Milestones PASSED
→ Phase PASSED

All Phases PASSED
→ Roadmap PASSED

Rules:

- A Day belongs to exactly one Week.
- A Week belongs to exactly one Milestone.
- A Milestone may contain multiple Weeks.
- A Day is the smallest progression unit.

# DD-005 — Week as Milestone Execution Unit

Status: Accepted

Implementation Status: Not Started

## Problem

The current system uses weeks primarily as containers for generated tasks.

This makes it unclear:

* What a week represents.
* How weeks relate to milestones.
* How progress should be calculated.

## Decision

A Week represents a milestone execution unit.

A week answers the question:

> "What part of this milestone will the learner work on this week?"

Weeks are no longer task containers.

Weeks contain Days.

Days are the smallest progression unit.

## Week Structure

```text
Week
├── week_id
├── roadmap_id
├── phase_id
├── milestone_id
├── week_number_global
├── week_number_in_milestone
├── title
├── goal
├── estimated_minutes
├── status
├── days[]
└── completion_rule
```

Example:

```text
week_id: week_001

roadmap_id:
goal_learn_embeddings_for_rag

phase_id:
P1

milestone_id:
M1.1

week_number_global:
1

week_number_in_milestone:
1

title:
Foundations of LLM Mental Models

goal:
Understand the basic mental model of how LLMs work and how prompts/tools guide behavior.

estimated_minutes:
150

status:
TODO

completion_rule:
all_days_passed
```

## Relationship to Days

A Week contains one or more Days.

Example:

```text
Week 1

Day 1: What is an LLM?
Day 2: How prompts guide behavior
Day 3: Tool use fundamentals
Day 4: Simple agent loop
Day 5: Review and validation
```

## Progression Rules

Week status is computed automatically from Day status.

The learner never updates Week status directly.

### Status Flow

```text
TODO
↓
IN_PROGRESS
↓
PASSED
```

or

```text
TODO
↓
IN_PROGRESS
↓
NEEDS_REVIEW
```

### Computation Rules

TODO

* No day started.

IN_PROGRESS

* At least one day started.

PASSED

* All days passed.

NEEDS_REVIEW

* One or more days failed.

## Source of Truth

Daily validation status is the source of truth.

Roadmap progress is computed from:

Day
→ Week
→ Milestone
→ Phase
→ Roadmap

Progress flows upward through the hierarchy.

# DD-006 — Milestone Completion Rules

Status: Accepted

Implementation Status: Not Started

## Problem

The current system mixes milestone progress, tasks, quiz validation, and learning completion.

This makes milestone progression difficult to reason about.

## Decision

Milestone completion is computed from Week completion.

Milestones are never updated directly.

## Status Model

Milestones use the same status model as all progression entities:

```text
TODO
IN_PROGRESS
PASSED
NEEDS_REVIEW
```

## Computation Rules

### TODO

No week has been started.

### IN_PROGRESS

At least one week has been started.

### PASSED

All milestone weeks have passed.

### NEEDS_REVIEW

One or more weeks require review.

## Example

```text
M1.1 Foundations

Week 1 = PASSED
Week 2 = PASSED

Result:

M1.1 = PASSED
```

Example:

```text
M1.1 Foundations

Week 1 = PASSED
Week 2 = NEEDS_REVIEW

Result:

M1.1 = IN_PROGRESS
```

## Source of Truth

Progress is computed hierarchically:

Day
→ Week
→ Milestone
→ Phase
→ Roadmap

No level may bypass the level below it.

## Curriculum Ownership

Milestones own the curriculum structure.

Roadmaps define milestones.

Milestones define weeks.

Weeks define days.

Days define learning content and validation.

Standalone task entities are not part of the progression model.


# DD-007 — Day Completion and Validation Model

Status: Accepted

Implementation Status: Not Started

## Problem

The current system stores multiple learning-related states:

* Task status
* Quiz validation
* Evidence score
* Learning validated flag

This creates ambiguity about what constitutes learning completion and what should drive progression.

## Decision

The Day becomes the smallest unit of progression and validation.

A Day is considered complete only through quiz validation.

Progression is based on PASS / FAIL rather than numerical scores.

## Day Completion Model

```text
Day
├── day_id
├── status
├── quiz_path
├── quiz_result
├── completed_at
├── reflection
└── review_reason
```

## Status Model

```text
TODO
IN_PROGRESS
PASSED
NEEDS_REVIEW
```

### TODO

Learning has not started.

### IN_PROGRESS

Learning content has been opened or partially completed.

### PASSED

The learner successfully completed the day's validation quiz.

### NEEDS_REVIEW

The learner failed the day's validation quiz.

## Quiz Result Model

```text
PASS
FAIL
```

### PASS

Quiz demonstrates sufficient understanding of the day's content.

Result:

```text
Day Status = PASSED
```

### FAIL

Quiz demonstrates insufficient understanding of the day's content.

Result:

```text
Day Status = NEEDS_REVIEW
```

## Examples

Successful completion:

```text
day_id: day_001

status: PASSED

quiz_path:
docs/quizzes/day_001.md

quiz_result:
PASS

completed_at:
2026-06-23T18:30:00

reflection:
"I understood the basic RAG pipeline."

review_reason:
""
```

Failed completion:

```text
day_id: day_002

status: NEEDS_REVIEW

quiz_path:
docs/quizzes/day_002.md

quiz_result:
FAIL

completed_at:
2026-06-24T19:10:00

reflection:
"I confused retrieval and generation."

review_reason:
"Weak answer on retrieval concepts."
```

## Progression Rules

Progression uses PASS / FAIL only.

Numerical scores do not influence progression.

The system may store evaluation feedback for user review, but progression logic ignores numerical grading.

## Source of Truth

Daily validation state is the source of truth.

Progress is computed hierarchically:

Day
→ Week
→ Milestone
→ Phase
→ Roadmap

No higher-level entity may bypass Day validation.

## Deferred Features

The following features are explicitly deferred:

* Numerical scoring
* Mastery levels
* Partial completion
* Question-level tracking
* Weighted progress calculations

These may be revisited in future design iterations if required.


# DD-008 — Target Learning Progression Architecture

Status: Accepted

Implementation Status: Not Started

## Problem

The current architecture mixes tasks, milestone tracking, quiz validation, and weekly learning content.

This makes progression difficult to reason about and difficult to evaluate.

## Decision

The target learning progression architecture will be day-centric.

The new progression flow is:

```text
Roadmap
→ Phase
→ Milestone
→ Week
→ Day
→ Learning Unit
→ Quiz
→ PASS / FAIL
````

## Entity Responsibilities

### Roadmap

Defines the long-term learning path.

Contains phases.

### Phase

Groups related milestones.

Progress is computed from milestone status.

### Milestone

Defines a meaningful curriculum objective.

Contains one or more weeks.

Progress is computed from week status.

### Week

Represents a milestone execution slice.

Contains one or more days.

Progress is computed from day status.

### Day

Smallest unit of progression.

Contains:

* Topic
* Learning content
* Quiz
* Validation result

Day status is the source of truth.

### Learning Unit

Contains the content the learner studies for a specific day.

It does not determine progress directly.

### Quiz

Validates the day’s learning unit.

Quiz result determines Day status.

## Progression Rule

Progress always flows upward:

```text
Day PASSED
→ contributes to Week PASSED

Week PASSED
→ contributes to Milestone PASSED

Milestone PASSED
→ contributes to Phase PASSED

Phase PASSED
→ contributes to Roadmap PASSED
```

## Explicitly Removed Concept

Standalone task entities are removed from the core progression model.

Activities such as:

* summarize a concept
* explain in your own words
* draw a pipeline
* answer a question
* design a small example

are modeled as quiz question types, not separate task objects.

## Source of Truth

The source of truth for progress is:

```text
Day validation status
```

not:

* task status
* evidence score
* learning_validated flag
* quiz score

## Implementation Implication

The current `tasks.csv` model should not remain the central progression table.

A new day-centric persistence model is required.

Possible future storage options:

* `data/days.csv`
* `data/learning_progress.json`
* `data/weeks.json`

Storage format is not decided in this decision.

## Evaluation Implication

Future evals should test:

1. Can the system generate a week for one milestone?
2. Does the week contain clearly separated days?
3. Does each day have learning content?
4. Does each day have a quiz?
5. Does quiz PASS mark the day as PASSED?
6. Does all days PASSED mark the week as PASSED?
7. Does all weeks PASSED mark the milestone as PASSED?

```

Next step: **DD-009 — Persistence Model**.
```

# DD-009 — Memory as Adaptive Teaching Context

Status: Accepted

Implementation Status: Not Started

## Problem

The system currently uses memory during planning and content generation.

However, memory should not directly influence learning progression.

Progression must remain deterministic and explainable.

## Decision

Memory will serve as an adaptive teaching context.

Memory may influence:

* How learning content is generated.
* How review content is generated.
* Which examples are selected.
* Which explanation style is preferred.
* Which concepts require additional reinforcement.

Memory may not influence:

* Day completion.
* Week completion.
* Milestone completion.
* Phase completion.
* Roadmap completion.

## Principle

```text
Progression = Deterministic

Memory = Personalization
```

## Learning Progression

Learning progression is determined exclusively through validation results.

```text
Quiz PASS
→ Day PASSED

Quiz FAIL
→ Day NEEDS_REVIEW
```

Memory does not override progression outcomes.

## Memory Responsibilities

Memory may store:

* Preferred explanation styles.
* Concepts the learner struggles with.
* Concepts the learner masters easily.
* Effective examples.
* Ineffective examples.
* Learning preferences.
* Relevant historical learning context.

Example:

```text
Learner repeatedly confuses:

- Retrieval
- Generation
```

This information may be used to improve future learning material.

## Review Flow

Example:

```text
Day Quiz
→ FAIL
→ Day Status = NEEDS_REVIEW
```

Memory may then assist in generating:

* Alternative explanations.
* Simpler examples.
* Additional practice questions.
* Different presentation styles.

Example:

```text
Previous explanation:
Abstract theory

Observed difficulty:
Learner struggled

Review content:
Concrete practical example
```

## Architecture Role

Memory is an auxiliary system.

Memory supports teaching effectiveness.

Memory is not part of the progression state model.

## Source of Truth

Learning progression is determined by:

```text
Day Status
Quiz Result
```

Memory is not a source of truth for progression.

## Target Architecture

```text
Roadmap
→ Phase
→ Milestone
→ Week
→ Day
→ Learning Unit
→ Quiz
→ PASS / FAIL

Memory
→ Personalization Layer
→ Content Adaptation
→ Review Adaptation
```

## Future Possibilities

Future versions may use memory to:

* Adapt learning difficulty.
* Recommend review content.
* Detect recurring knowledge gaps.
* Personalize learning paths.

These adaptations must not directly modify progression status.


# DD-010 — Learning Progress Persistence Model

Status: Accepted

Implementation Status: Not Started

## Problem

The current implementation stores learning progress primarily in `tasks.csv`.

With the new day-centric architecture, tasks are no longer the core progression entity.

A new persistence model is required to support the hierarchical learning structure.

## Decision

The source of truth for learning progression will be a hierarchical JSON document.

```text
data/learning_progress.json
```

This file stores the learner's current progression through the roadmap.

Generated Markdown files remain presentation artifacts and are not considered part of the progression state.

## Learning Progress Hierarchy

```text
Roadmap
└── Phase
    └── Milestone
        └── Week
            └── Day
```

## Proposed Structure

```text
learning_progress.json

Roadmap
├── roadmap_id
├── status
└── Weeks
    ├── week_id
    ├── phase_id
    ├── milestone_id
    ├── week_number_global
    ├── week_number_in_milestone
    ├── title
    ├── goal
    ├── status
    └── Days
        ├── day_id
        ├── day_number
        ├── topic
        ├── estimated_minutes
        ├── learning_unit_path
        ├── quiz_path
        ├── status
        ├── quiz_result
        ├── completed_at
        ├── reflection
        └── review_reason
```

## Source of Truth

The following file becomes the single source of truth for learning progression:

```text
data/learning_progress.json
```

Progression is computed exclusively from this file.

## Generated Artifacts

The following files are generated outputs and are not considered progression state:

* `docs/learning_units/*.md`
* `docs/quizzes/*.md`
* `weekly_plans/*.md`

These files may be regenerated if necessary.

## Rationale

A hierarchical JSON structure naturally mirrors the learning architecture:

```text
Roadmap
→ Phase
→ Milestone
→ Week
→ Day
```

Compared to a flat CSV model, this approach:

* Better represents the learning hierarchy.
* Simplifies progression computation.
* Keeps related learning state together.
* Reduces ambiguity between planning and progression.

## Future Considerations

This decision does not define the physical storage technology permanently.

If scalability or synchronization requirements change, the persistence layer may later be replaced by a database while preserving the same logical hierarchy.


# DD-011 — Review Flow and Review Day Generation

Status: Accepted

Implementation Status: Not Started

## Problem

The learning system must support learners who do not successfully complete a day's validation.

The review mechanism should:

* Reinforce learning.
* Preserve learning history.
* Minimize unnecessary LLM generation.
* Keep progression deterministic.
* Avoid modifying previously generated plans.

## Decision

When a learner fails a day's quiz, the system will generate a dedicated **Review Day**.

A Review Day is a new learning unit focused exclusively on the failed day's concepts.

The original Day remains part of the learner's history and is never overwritten.

## Review Flow

```text
Day Learning
        ↓
Day Quiz
        ↓
     PASS / FAIL
        │
        ├── PASS
        │      ↓
        │   Day = PASSED
        │
        └── FAIL
               ↓
      Day = NEEDS_REVIEW
               ↓
User selects:
"Generate Review Day"
               ↓
Review Day Generated
               ↓
Review Learning Unit
               ↓
Review Quiz
               ↓
PASS / FAIL
```

## User Interaction

Review generation is explicitly initiated by the learner.

Example:

```text
Day 2
Status:
NEEDS_REVIEW

Button:

Generate Review Day
```

The system does not automatically regenerate review content.

## Review Day

A Review Day belongs to the same:

* Roadmap
* Phase
* Milestone
* Week

The Review Day references the failed day.

Example:

```text
Week 1

Day 1
Day 2
Day 2R
Day 3
Day 4
Day 5
```

Where:

```text
Day 2R

review_of_day = Day 2
```

## Generation Scope

Review generation is intentionally limited.

The LLM receives only the information required to regenerate the failed learning experience.

Inputs:

* Failed Day
* Original learning unit
* Quiz feedback
* Relevant memory context

Outputs:

* Review Learning Unit
* Review Quiz

The system must **not** regenerate:

* The roadmap
* The milestone
* The week
* Previously completed days
* Future days

Only the Review Day is generated.

## Memory Usage

Memory supports review generation but does not determine progression.

Examples of useful memory:

* Frequently misunderstood concepts.
* Preferred explanation style.
* Previous successful examples.
* Concepts requiring reinforcement.

Memory is used only to improve the quality of the regenerated learning material.

## Progression Rules

The original Day remains:

```text
NEEDS_REVIEW
```

until the associated Review Day has been successfully completed.

A Week cannot be marked as PASSED until all required Days, including any generated Review Days, have been passed.

Progression therefore remains deterministic:

```text
Day
→ Week
→ Milestone
→ Phase
→ Roadmap
```

## Preservation of Learning History

The system never overwrites previously generated learning artifacts.

The original Learning Unit, Quiz, Quiz Feedback, and Day Status remain available for inspection.

Review content is stored as a new learning attempt linked to the failed Day.

This preserves a complete learning history while allowing the learner to improve.

## Efficiency Principle

Review generation is designed to minimize LLM usage.

Only a single Review Day is generated.

Previously generated Weeks, Days, Learning Units, and Quizzes are reused whenever possible.

No unnecessary regeneration of existing content is permitted.

## Rationale

This approach provides several advantages:

* Preserves an auditable learning history.
* Avoids unnecessary token consumption.
* Keeps review generation localized.
* Prevents changes to already approved learning plans.
* Enables adaptive teaching through memory while maintaining deterministic progression.
