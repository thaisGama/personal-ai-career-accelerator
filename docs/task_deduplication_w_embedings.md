# 📄 Mini-Project Guide - Task Deduplication with Embeddings

Goal

Automatically group semantically similar work tasks so that monthly summaries do not contain duplicates written in different ways.

Example input
Daily sync with marketing team
Recurring marketing meeting, marketing standup
Prepare Q3 budget
Budget planning meeting

Desired output
Group 1 — Marketing sync
- Daily sync with marketing team
- Recurring marketing meeting
- Marketing standup

Group 2 — Budget planning
- Prepare Q3 budget
- Budget planning meeting


No LLM required.
Just embeddings + similarity.

Why embeddings are the right tool

This is a semantic similarity problem.

Why naive approaches fail

Exact string matching misses paraphrases

Rule-based normalization does not scale

Manual standardization is brittle

Why embeddings work

Meaning matters more than wording

Tasks are short, noisy text

“Same idea, different phrasing” is common

End-to-End Pipeline (Realistic)
Raw task input (messy text)
→ parse & split
→ clean & normalize
→ atomic tasks (one task = one unit)
→ embed (one vector per task)
→ similarity comparison
→ grouping / clustering
→ human-readable summary


Each arrow represents a deliberate decision, not magic.

Step 1 — Parse Raw Input (Very Important)

Real task input is messy.

Example raw input from a text box:

Daily sync with marketing team
Recurring marketing meeting, marketing standup
Prepare Q3 budget

Parsing strategy (simple and robust)

Split by newline

Split each line by comma

Trim whitespace

Drop empty entries

Conceptual pseudocode
raw_text = ...

tasks = []
for line in raw_text.split("\n"):
    for part in line.split(","):
        task = part.strip()
        if task:
            tasks.append(task)


Result:

[
  "Daily sync with marketing team",
  "Recurring marketing meeting",
  "Marketing standup",
  "Prepare Q3 budget"
]

Step 2 — Normalize (Lightly)

Recommended:

lowercase

trim extra spaces

Avoid:

stemming

lemmatization

stopword removal

Modern embedding models already handle language well.

Step 3 — Represent Tasks Explicitly

Each task must be an atomic semantic unit.

A table-like structure is ideal (pandas is perfect):

task_id	task_text
1	daily sync with marketing team
2	recurring marketing meeting
3	marketing standup
4	prepare q3 budget

This makes the system:

debuggable

traceable

easy to reason about

Step 4 — Generate Embeddings

Each task text is embedded independently.

Conceptually:

embeddings = embed(task_texts)


Key points:

same embedding model for all tasks

same preprocessing

fixed-size vectors

Step 5 — Measure Similarity

Use cosine similarity.

Why:

ignores verbosity

focuses on meaning

works well for short text

This gives you a task ↔ task similarity matrix.

Step 6 — Group Tasks
Option A — Threshold-based grouping (recommended first)
SIMILARITY_THRESHOLD = 0.85


If similarity between two tasks exceeds the threshold → same group.

Pros

simple

transparent

easy to tune

Cons

requires threshold tuning

Option B — Clustering (later)

Examples:

hierarchical clustering

DBSCAN

Use this only when:

number of tasks grows large

threshold logic becomes messy

Step 7 — Produce Output

Group tasks and label clusters manually or heuristically.

Example:

Group: Marketing sync
- daily sync with marketing team
- recurring marketing meeting
- marketing standup


This is already job-useful output.

Debugging Guide

Problem: Unrelated tasks grouped together
→ threshold too low

Problem: Similar tasks not grouped
→ threshold too high or task text too short

Problem: Ambiguous grouping
→ improve task descriptions slightly

Done Criteria

You can consider this mini-project complete when:

Similar tasks group correctly

Unrelated tasks stay separate

You can explain why tasks were grouped

Adjusting one parameter improves results

If you meet these → you are operationally competent with embeddings.

What This Teaches You (Career-Relevant)

This exact pattern appears in:

task deduplication

ticket grouping

log aggregation

memory compression

semantic search

This is real AI Engineer work, not a toy example.