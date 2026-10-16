# Learning Purpose MVP (#19)

Learning Purpose reuses the existing roadmap → weekly plan → day → learning unit
→ quiz → progress workflow. Roadmaps remain mandatory, including for a goal
that needs only one phase and one milestone. No separate agents, persistence
stores, evaluation runner, certification readiness scoring, or interview engine
are introduced.

## Selection and persistence

The sidebar offers Certification Preparation, Topic Mastery, and Career
Development. Interview Preparation is shown as a disabled **Coming soon** button
next to the selector: Streamlit's selectbox cannot disable an individual option.
It cannot be submitted as a supported purpose through the service either.

Application-owned roadmap `learner_setup.learning_purpose` stores one of:

- `certification_preparation`: exam-relevant explanations, scenarios, objectives,
  and knowledge checks; no invented official blueprint or readiness claim.
- `topic_mastery`: essential concepts, practical application, and understanding
  checks, with scope proportional to the stated topic.
- `career_development`: competencies and workplace deliverables for the career
  stated in the goal.

The selected saved roadmap restores its purpose read-only, along with its time
limits, intensity, and other setup. Switching back to a new goal preserves its
separate draft purpose. Model-authored metadata cannot overwrite these settings.

Roadmap filenames still use the goal slug. When a new goal resolves to an existing
roadmap with a different purpose, generation stops with guidance to select that
roadmap or explicitly force regeneration. Purpose selection never silently
rewrites that saved roadmap. As before, forcing regeneration replaces that
roadmap; give separate goals distinct names to retain separate roadmaps.

## Compatibility

A complete saved setup missing **only** `learning_purpose` gets
`career_development` in memory. Loading/restoring it does not rewrite its JSON,
Markdown, curriculum, IDs, quiz history, or progress. This matches the original
career-oriented application. Explicit invalid values (including Interview
Preparation) and other incomplete/invalid setup remain errors rather than being
silently replaced with defaults.

Historical day material whose roadmap file is absent still uses the existing
unscoped generation/grading prompts. The application does not invent missing time
limits or a new roadmap association for it. New planner routes always require a
roadmap. If the owning file exists but its setup is invalid, day generation or
grading reports that error rather than borrowing setup from the currently open
roadmap.

## Shared propagation and prompt selection

- Planner service stores the purpose in setup and passes it through both direct
  generation and the existing ReAct preferences payload.
- Roadmap generation selects the unchanged `roadmap.system` only for Career
  Development goals explicitly naming AI/ML Engineering or AI Generalist
  (including the expanded Artificial Intelligence / Machine Learning names).
  This retains the original mandatory AI Engineer spine and resource rules.
- Other purposes and other careers select `roadmap.focused_system`, using the
  same JSON schema, validation, persistence, and task seeding. One milestone is
  already valid in that schema; no new curriculum model is needed.
- Shared weekly and learning-unit builders append versioned purpose guidance.
  Learning units use the learner's goal as their default target rather than
  assuming an AI Engineering role for every goal. Existing output shapes and
  quality-repair flows remain shared.
- Day units, quizzes, and grading load setup through the day's owning
  `week.roadmap_id`; they do not use the active UI selection. Day units also use
  the saved preferences, background, and intensity. Review days use the same
  route and owning week.
- Quiz bindings, saved quiz hashes, roadmap/week/day checks, completion rules,
  and append-only history remain unchanged. Purpose does not loosen day scope
  or imply that a quiz establishes certification readiness.

New prompt IDs (all initially `1.0.0`): `roadmap.focused_system`,
`purpose.context`, `purpose.certification_preparation`, `purpose.topic_mastery`,
and `purpose.career_development`. They use the existing small loader and metadata
API. All 28 PR 2 template files/versions remain unchanged. For a composed prompt,
record its base template metadata and the purpose templates in any future
consumer; there is no evaluation reporting in this change.

## Time limits

Purpose guidance explicitly includes saved weekly hours and maximum session
minutes and gives them precedence over generic example durations and day counts.
Exercises/projects must be split into sessions within those limits. The planner
also checks parsed learning-day durations before generating the weekly learning
unit or saving the plan: durations must be explicit and positive, each must fit
the session limit, and their sum must fit weekly minutes. Violations produce a
normal generation error; there is no additional paid retry.

The check covers the scheduled learning days, not an estimate of the time needed
to read arbitrary generated prose or complete optional enrichment. Review days
retain existing scheduling behavior. Certification scope comes from the stated
goal and context; full blueprint ingestion is deferred. AI career matching is a
small explicit phrase check, not a semantic career classifier: name the target
career clearly in the goal.

## Validation

Mocked tests cover all three purposes through direct/ReAct persistence, restoring
legacy files without migration, template selection (including other careers),
single-milestone roadmaps, forwarding purpose/time to shared prompts, rejecting
oversized schedules, read-only UI restore/draft switching, and day-unit → quiz →
grading completion with isolation from another roadmap. The Interview placeholder
is disabled in UI and rejected by setup validation. No live or paid model calls
are used.

The PR 2 production golden fixture deliberately changes only its two roadmap
cases for the new purpose-aware selection; its other 18 cases and all original
template hashes remain unchanged. New purpose-context goldens and metadata cover
the additional templates.
