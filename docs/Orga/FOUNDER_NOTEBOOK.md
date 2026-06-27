# Product Roadmap (6 Weeks)

## Week 1-2: Understand & Stabilize

Goal:
Understand the current system end-to-end.

Deliverables:

[ ] Document architecture
[ ] Document system flow
[ ] Document tools
[ ] Document memory
[ ] Create EVALS.md
[ ] Run Eval 1 - New User
[ ] Run Eval 2 - Returning User
[ ] Run Eval 3 - Failed Quiz
[ ] Identify top 3 weaknesses

Success Criteria:

- I can explain the system from user input to final output.
- I understand what memory stores.
- I understand where memory is used.
- I understand what each tool does.
- I understand the role of the controller.
- I understand whether quiz results affect planning.
- I understand the role of the critic.

---

## Week 3: Market Awareness MVP

Goal:
Make learning recommendations aware of market demand.

Deliverables:

* [ ] Collect 5-10 AI job descriptions
* [ ] Extract required skills
* [ ] Group skills into categories
* [ ] Create first skill-gap analysis workflow

Success Criteria:

* Given a job description, the system identifies missing skills.

---

## Week 4: Connect Skill Gaps to Roadmaps

Goal:
Personalize learning based on market requirements.

Deliverables:

* [ ] Feed skill gaps into roadmap generation
* [ ] Feed skill gaps into weekly planning
* [ ] Test with real AI Engineer jobs

Success Criteria:

* Roadmaps change based on target job requirements.

---

## Week 5: Dogfooding

Goal:
Use the system for my own career transition.

Deliverables:

* [ ] Analyze 5 target jobs
* [ ] Generate my own gap analysis
* [ ] Generate my own roadmap
* [ ] Follow recommendations

Success Criteria:

* I would trust the system enough to use it myself.

---

## Week 6: Demo & Publish

Goal:
Turn the project into a portfolio asset.

Deliverables:

* [ ] Record demo
* [ ] Clean GitHub repository
* [ ] Create architecture overview
* [ ] Publish LinkedIn post

Success Criteria:

* Public demo exists.
* Portfolio-ready project exists.

```
```

# Known Gaps

- No market awareness
- Memory unclear
- No eval suite

# Parking Lot

Ideas NOT being worked on now:

- Interview coach
- Resume coach
- Application tracker
- Multi-agent redesign
- Cost tracker - heard from chip huyen web search for example increases costs significantly. Would like to see the difference. Then can decide if use classical coding for scraping jobs
- cost optimization possibilities: use classical ML to classify request. If request is Q&A pertinent don't call expensive model!
- use semantic search first for user query, if no match, only then call LLM!
- If user failed a quiz, maybe the next week should explain the concept differently instead of repeating the same material. Not sure current memory system can support this. Potential future experiment.

# Next Milestone:

- Market Awareness MVP