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
- Connect the existing general task-quiz interface to an explicitly selected day;
  task quiz results are not automatically inferred to validate a day.
- Review-resolution semantics, advanced navigation, and View Plans redesign.
- Existing ReAct behavior can save repeated weeks when a generated learning unit
  is absent. This MVP displays recorded weeks and does not alter generation policy.

Sprint project: https://github.com/users/thaisGama/projects/2

No sprint issues were found in the repository. Earlier issue creation was denied
by the GitHub integration, so no issue numbers can truthfully be referenced.
