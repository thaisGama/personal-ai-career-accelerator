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

------------------------------------------------------------
## Previous draft!!! se if still useful
# Eval 1 - New User

## Purpose

Verify the system can create a complete learning experience for a new user.

## Input

Goal:
Become AI Engineer

Time:
5h/week

## Expected

* Roadmap generated
* Weekly plan generated
* Tasks generated
* Learning unit generated

## Actual

NOT RUN

## Result

NOT RUN

## Observations

*

## Action Items

*

---

# Eval 2 - Returning User

## Purpose

Verify the system continues an existing roadmap instead of starting over.

## Input

Goal:
Become AI Engineer

Context:
Existing roadmap and tasks

## Expected

* Existing roadmap reused
* Progress respected
* Weekly plan continues current milestone

## Actual

NOT RUN

## Result

NOT RUN

## Observations

*

## Action Items

*

---

# Eval 3 - Failed Quiz

## Purpose

Verify quiz results influence future planning.

## Input

Goal:
Become AI Engineer

Context:
Weak performance on embeddings quiz

## Expected

* Embeddings identified as weak topic
* Weekly plan reinforces embeddings
* Roadmap progression adapts

## Actual

NOT RUN

## Result

NOT RUN

## Observations

*

## Action Items

*
