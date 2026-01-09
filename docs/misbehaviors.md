# Agent Misbehaviors Registry (AMR)
A living registry of failure patterns observed in this project’s agents (runtime + dev).
Goal: prevent repeated mistakes by turning each misbehavior into:
- a rule (prevent)
- a detector (how we know it happened)
- a fix (what to do next time)

This file is loaded at runtime and treated as HARD CONSTRAINTS.

---

## How to use this file
### When to add an entry
Add a new entry when:
- a failure repeats more than once
- a failure wastes >10 minutes
- a failure creates wrong outputs confidently
- a failure causes loops, broken artifacts, or confusing UX

### How to write an entry (template)
**Symptom** → what you observed  
**Likely cause** → why it happens  
**Prevent** → hard rule(s) the agent must follow  
**Detect** → a check the system/critic can apply  
**Fix** → the smallest safe correction step  
**Evidence** → where you saw it (trace/log/screenshot)

---

# Section A — Runtime agent misbehaviors (Planner / Quiz / Controller)

## AMR-R001 — Tool loop / repeated tool calls
**Symptom**
- Controller calls the same tool repeatedly (e.g. retrieve_memory 2–3×) and hits a safety stop.

**Likely cause**
- Uncertainty → retries instead of progressing.

**Prevent**
- Never call the same tool more than once in a run unless explicitly allowed.
- If retrieve_memory returns 0 hits: do not call it again in the same run.

**Detect**
- same_tool_count >= 2
- OR (tool == retrieve_memory AND hits == 0 AND called_again == true)

**Fix**
- Skip retrieval and proceed with a “best-effort” plan using only provided context.
- If still blocked: trigger fallback tool order (safe path).

**Evidence**
- Trace shows repeated calls to the same tool.

---

## AMR-R002 — Controller output not strict JSON
**Symptom**
- Controller returns prose, markdown, code fences, or invalid/malformed JSON.

**Likely cause**
- Prompt drift, formatting non-compliance.

**Prevent**
- Controller must output ONE JSON object only.
- Output must start with `{` and end with `}`.
- No markdown. No code fences. No extra text.

**Detect**
- JSON parse failure OR extra leading/trailing characters.

**Fix**
- One retry with a “format correction” instruction.
- If still invalid: follow deterministic safe path (no LLM decision).

---

## AMR-R003 — Missing or broken output markers (plan/post separation)
**Symptom**
- Weekly plan markers are missing or duplicated; downstream parsing fails.

**Likely cause**
- Planner did not follow output contract.

**Prevent**
- Planner must always output required markers exactly once:
  - <<PLAN_MARKDOWN>> ... <<END_PLAN>>
  - <<LINKEDIN_POST>> ... <<END_LINKEDIN_POST>> (if applicable)

**Detect**
- Marker not found OR multiple occurrences OR extracted section empty.

**Fix**
- “Rewrap-only” regeneration: preserve content, only reformat into correct markers.

---

## AMR-R004 — “next_task” degenerates into generic fallback
**Symptom**
- next_task becomes a generic fallback (e.g., “Review the weekly plan...”) even though actionable items exist.

**Likely cause**
- Next Actions section missing, inconsistent heading, or not in bullet format.

**Prevent**
- Weekly plan must include a section titled exactly: `✅ Next Actions`
- Provide 3–7 bullet items, each actionable.

**Detect**
- next_task == fallback AND plan_length > threshold
- OR missing `✅ Next Actions`

**Fix**
- Repair only the `✅ Next Actions` section (do not change the rest).
- Then re-run next_task selection.

---

## AMR-R005 — Micro-tasks are vague / not executable
**Symptom**
- Tasks read like goals (“learn about X”) without a concrete output or done-check.

**Likely cause**
- Planner optimizing for inspiration instead of execution.

**Prevent**
Every micro-task MUST include:
- Duration (10–30 min)
- Output artifact (file, snippet, checklist, commit, screenshot)
- Done-check (how to verify)

**Detect**
- Missing duration OR missing output OR missing done-check
- Overuse of vague verbs: “explore”, “learn”, “understand” without deliverable

**Fix**
- Rewrite tasks into action + artifact form.
- Reduce scope until it fits 10–30 minutes.

---

## AMR-R006 — Memory injection too long or irrelevant
**Symptom**
- Plan becomes anchored to irrelevant history, or prompt becomes bloated.

**Likely cause**
- Retrieval returns loosely related snippets; no summarization.

**Prevent**
- Cap injected memory size (e.g., <= 2000–3000 chars).
- Always summarize retrieved memory into 3 bullets before using it.

**Detect**
- memory_chars > cap OR plan references old topics without user intent.

**Fix**
- Replace raw memory injection with a short “Memory Summary” block.

---

## AMR-R007 — Task store drift (duplicates across weeks)
**Symptom**
- Same tasks reappear as new tasks week after week with slightly different names.

**Likely cause**
- Unstable titles; weak dedup key.

**Prevent**
- Task titles follow: `[Topic] Verb + object`
- Normalize titles before writing to tasks store.
- Dedup by (topic + normalized_title).

**Detect**
- High “created” count with similar embeddings / similar normalized titles.

**Fix**
- Apply normalization + dedup before insert/upsert.

---

# Section B — Dev-agent misbehaviors (future “team” of coding agents)

## AMR-D001 — Changes without evidence
**Symptom**
- Agent claims “fixed” without tests, logs, or reproduction steps.

**Prevent**
- No task is DONE unless evidence is provided:
  - commands run + outputs
  - tests passing (or explicit reason not possible)

**Detect**
- Report lacks “How tested” section.

**Fix**
- Require a follow-up run that produces evidence or revert the change.

---

## AMR-D002 — Scope creep / unrelated refactors
**Symptom**
- Agent touches unrelated files, renames broadly, or reformats large areas.

**Prevent**
- Only change files needed for the ticket.
- No “drive-by refactors” unless requested.

**Detect**
- Diff touches >N files or unrelated directories.

**Fix**
- Revert unrelated changes; isolate into separate PR if truly needed.

---

## AMR-D003 — Breaking interfaces silently
**Symptom**
- API/CLI/UI behavior changes without updating docs/tests.

**Prevent**
- Any interface change requires:
  - updated tests
  - updated docs/README
  - migration note (if needed)

**Detect**
- Changed function signatures/routes without corresponding updates.

**Fix**
- Add compatibility layer or update dependent code + docs.

---

## AMR-D004 — UI changes without screenshots or a smoke checklist
**Symptom**
- UI/UX changes land with no proof they render correctly.

**Prevent**
- Any UI change must include:
  - screenshot(s) or a short screen recording OR
  - a reproducible smoke test checklist

**Detect**
- PR report lacks “UI proof”.

**Fix**
- Run UI and attach proof; otherwise do not merge.

---

# Appendix — Allowed exceptions
- A tool may be called twice only if explicitly allowed in the controller policy AND the agent records a reason.
- Emergency “safe path” is allowed when controller output is invalid after one retry.
