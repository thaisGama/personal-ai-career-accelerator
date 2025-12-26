
# Personal AI Career Accelerator
### *Your AI-powered system for learning, building, and advancing in 30-minute sessions — built for busy professionals.*

---

## 🌍 Why This Exists
Most ambitious professionals — especially working parents — simply **don’t have the time or energy** to stay updated in AI/ML.

Yet the world moves fast.  
To avoid falling behind, you need:

- fast, structured learning  
- visible progress  
- real portfolio projects  
- consistency  
- motivation  
- tools that reduce cognitive load  

This project builds exactly that:  
a personal **AI Career Accelerator** powered by an **AI Weekly Planner Agent**.

---

## 🧠 How It Works

A modern AI-powered learning system consists of:

### ✔ LLM → *thinks*  
Understands your goals and generates plans.

### ✔ Embeddings + Vector Search → *remembers*  
Stores your knowledge and progress.

### ✔ Agent Logic → *plans & decides*  
Creates micro-tasks, picks projects, and adapts weekly.

### ✔ Tools → *acts*  
Writes files, organizes your tasks, generates posts.

Your Weekly Planner Agent follows this architecture.

---

## 🚀 What This Project Does
At its core, this repo contains an AI agent that:

### 🎯 Generates a Weekly Learning Plan  
Personalized based on your goals and available time.

### 🧩 Breaks it into Micro-Tasks  
Perfect for 10–20–30 minute sessions.

### 🛠 Suggests a Mini-Project  
So you build portfolio pieces every week.

### 📝 Creates a LinkedIn Post Template  
Keeping your public visibility consistent.

### 💾 Automatic Markdown Output  
All files are saved into well-structured folders.

---

## 👥 Who This Is For
- Busy professionals  
- Working moms & dads  
- Full-time employees  
- Career changers  
- Anyone overwhelmed by too much content  
- Learners who want **small wins** instead of burnout  
- People aiming for a better job or to build a monetizable AI product  

---

# 📅 4-Week Roadmap (Phase 1)

## 📆 Week 1 — Modern AI Foundations + Agent MVP
- Learn LLMs, embeddings, agent workflows  
- Build the initial Weekly Planner Agent  
- Generate first weekly plan + LinkedIn post  
- Push first commits to GitHub  

---

## 📆 Week 2 — Applied AI Feature (Core Module)
Build one applied module (your future product core):

- Course → Micro-Lesson Summarizer  
- Journaling → Insight Generator  
- Learning → Portfolio Artifact Creator  

---

## 📆 Week 3 — Real AI App (UI + Vector Search + Agents)
Assemble your modules into a Streamlit app:

- Upload notes/course text  
- Generate summaries  
- Produce weekly plans  
- Memory via embeddings  
- Optional audio summaries  

---

## 📆 Week 4 — Monetization + Career Positioning
- Build landing page  
- Polish UI  
- Deploy app  
- Publish updates  
- Design “Pro Version”  
- Prepare job search materials  

---

# 📂 Repo Structure
```
agent/               # Weekly Planner Agent code  
weekly_plans/        # Generated learning plans  
tasks/               # 30-minute tasks  
posts/               # LinkedIn post drafts  
docs/                # Memory, learning notes, summaries  
```

---

# 🛠 Tech Stack
- Python  
- OpenAI / LLMs  
- Basic agent patterns  
- (Future) embeddings + vector search  
- (Future) Streamlit UI  

---

# 🌟 Long-Term Vision
This project will grow into a SaaS platform for:

- busy professionals  
- working parents  
- ambitious learners  
- people transitioning to AI careers  

Planned future features:

- audio lessons  
- smart task prioritization  
- portfolio generator  
- interview prep  
- dashboards with insights  
- personalized AI learning paths  

---

# ✔ Status
Week 1 in progress.  
Planner Agent v0.1 under development.

---

## 🧭 Learning Check (Quiz) v0.1
- Run `streamlit run app.py` (with `OPENAI_API_KEY` set), open the **Learning Check** section, enter a topic and optional notes, then click **Generate quiz**.
- Paste your answers in the UI and click **Evaluate answers** to get a mastery score and move-on recommendation. Results are saved under `docs/quizzes/`.
- Click **Append to memory.md** to drop the evaluation into `docs/memory.md` for future context.
- The quiz UI now shows only questions by default; rubric is in an expander and answers stay locked until you evaluate (or manually unlock).
- CLI smoke test: `python scripts/run_learning_check.py` (requires `OPENAI_API_KEY`).
