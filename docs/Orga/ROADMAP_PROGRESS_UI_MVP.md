# Roadmap progress and learning context MVP

Implemented on `feature/roadmap-progress-ui` for one PR targeting `master`.

Selecting an existing roadmap establishes shared planner, progress, library,
and task-quiz context. Switching roadmaps clears old previews, quiz answers,
and library selections. The Roadmaps tab remains an independent browser.

The planner shows quiz-validated core-day progress, separately counted review
days, expandable weeks, and a recommended day before generation. Its action
opens linked day material or a clearly labeled week overview in the Learning
Library. Missing day material can be generated through the existing day tool;
offline mode disables generation. Generating or opening content never marks a
day completed.

The library filters by explicit saved-path links and shows roadmap, week, day,
topic, and status where available. Week material is labeled as an overview and
never given an invented day. Content files are unchanged by browsing.

## Data and completion rules

- A day's recorded `quiz_result: PASS` means Completed; `FAIL` means Needs review.
- Task DONE and aggregate week/roadmap status do not establish day completion.
- Core progress measures linked, saved core days, not an estimated curriculum total.
- Missing or contradictory quiz metadata prevents a percentage being displayed.
- Reviews are distinguished using existing `is_review` / `review_of_day_id` fields.
- Passing a review does not automatically resolve its original day; remediation
  behavior remains unchanged.
- Both weekly generation routes now record `roadmap_id`, `plan_path`, and the
  optional week-level `learning_unit_path` on the existing week record.
- Day generation uses its owning week's roadmap ID rather than the global header.
- Duplicate learning-unit path associations are treated as unknown.

Historical progress has weeks for several goals under one file-level roadmap ID,
and historical weekly units have no explicit links. The UI does not infer
ownership from that header, filenames, matching topics, or task completion.
Those records show unavailable progress/context until reliable associations
exist. They are not migrated or rewritten. General library browsing without a
selected roadmap still exposes historical units with a context-unavailable note.

View Plans is not redesigned. Loading an unlinked plan into the active roadmap's
planner preview is disabled to avoid introducing unrelated content.

## Validation

Automated Streamlit AppTest scenarios cover two-roadmap isolation, switching,
continuation, mock day generation, completed/failed/review day presentation,
day and week headers, and unknown historical metadata. Pure helper tests cover
exact-path associations, conflicting links, read-only fallbacks, and quiz-based
completion. Existing generation tests cover saved links in direct and ReAct
routes. Run the complete suite with:

```bash
.venv/bin/python -m pytest -q
```

No paid API calls are used by these tests. Interactive browser visual verification
was unavailable in the execution environment; verify layout and tab transitions
manually before merging.

## Deferred follow-ups

- Explicitly link historical records if a trustworthy source becomes available.
- Review-resolution semantics, advanced navigation, and View Plans redesign.
- Existing ReAct behavior can save repeated weeks when a generated learning unit
  is absent. This MVP displays recorded weeks and does not alter generation policy.

Sprint project: https://github.com/users/thaisGama/projects/2

No sprint issues were found in the repository. Earlier issue creation was denied
by the GitHub integration, so no issue numbers can truthfully be referenced.

## Day-linked quiz workflow fix

The Quiz tab originally called only the standalone topic/task service. Roadmap
filtering of tasks never established a day association, and generic quiz results
could not update day completion.

The Quiz tab now resolves an explicitly selected library day first, otherwise
the recommended day. An incomplete explicit selection blocks generation rather
than falling back to another day. The header identifies roadmap/week/day/topic;
the linked topic is read-only. Library default selection prefers recommended
material; without a recommendation, historical browsing requires an explicit
choice. Standalone quizzes keep the existing editable topic workflow.

Linked generation reuses the existing day quiz tool with the day topic,
objectives when recorded, and saved day content. The week goal is background
only. Roadmap-wide tasks and manual context notes do not broaden its scope:
current task records lack a reliable day association, so filtering is omitted.

Generation retains a copied roadmap/week/day binding, topic, quiz ID, saved path,
and content hash in session state. Evaluation validates that identity against
saved progress and grades the exact generated snapshot, even if a later quiz
generation changes the day's current quiz path. The existing MOVE_ON/PASS and
REPEAT/FAIL grading and progress rules remain unchanged.

### Backward-compatible persistence extension

- New UI-generated day quizzes use an optional unique quiz-ID filename suffix;
  regenerating a day preserves its earlier quiz files. Existing callers retain
  their original filenames unless they supply a quiz ID.
- Submitted day results append `record_type: day_quiz` entries to the existing
  `data/quiz_results.jsonl`, including the copied roadmap/week/day identity,
  quiz ID/path/hash, topic, quiz snapshot, answers, evaluation, and timestamp.
- Previous task result entries remain untouched and readable as JSON lines.
- No progress schema changes or historical migrations are introduced by this fix.
- Unsubmitted quiz drafts and answers survive context changes in session state,
  with a warning and download action; they do not survive an application/session
  restart unless downloaded. They are never reassigned to a new day.
- Linked results rerun the UI so the overview updates immediately. Standalone
  results do not affect roadmap day completion.

### Manual verification

1. Select `api_gateway_vs_alb`. Confirm Week 1 / Day 1 and the read-only topic
   `Understanding API Gateway` appear in Learning Check.
2. Generate a Day 1 quiz and check that questions use its lesson material.
3. Submit answers; confirm only Day 1 becomes Completed or Needs review and the
   Progress Overview updates without roadmap regeneration.
4. Explicitly select another linked day in the library. Confirm its topic and
   identifiers replace the recommendation; generate a quiz for that day.
5. Enter answers without submitting, then change day or roadmap. Confirm the
   old preview cannot be submitted for the new context and its draft is available
   under Preserved previous quiz drafts and answers.
6. Switch to the new-goal route or a roadmap without a determinable day. Confirm
   the editable standalone topic workflow remains available.

No paid API calls are required for automated tests. Interactive visual
verification is still pending a connected browser.
