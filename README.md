# AI Career Learning Assistant

### *An AI system that generates structured learning plans, tasks, and feedback loops for busy professionals.*

---

## 🚀 Problem

Learning AI while working full-time is unstructured, overwhelming, and hard to sustain.
Most resources are scattered, and there is little guidance on:

* what to learn next
* how to stay consistent
* how to turn learning into real portfolio work

---

## 💡 Solution

This project is an **AI-powered learning assistant** that:

* generates structured weekly learning plans
* breaks them into actionable micro-tasks
* adapts over time using memory and feedback
* helps maintain progress without heavy manual planning

It acts as a lightweight **AI coach for continuous skill development**.

---

## 🧠 System Overview

This is a **multi-component AI system**, not just a prompt.

### Core components:

* **LLM (Planner)** → generates weekly plans and learning content
* **Embeddings + Vector Search (Memory)** → retrieves relevant past learning context
* **Agent Loop (ReAct-style)** → orchestrates multi-step reasoning and tool usage
* **Task System** → tracks progress and updates learning state
* **Quiz System** → evaluates understanding and identifies weak areas
* **Trace Logging** → records agent steps for transparency and debugging
* **Streamlit UI** → user interface to run and inspect the system

---

## ⚙️ What the System Does

* 📅 Generates a personalized weekly learning plan
* 🧩 Breaks it into 10–30 min micro-tasks
* 🛠 Suggests a weekly mini-project
* 📝 Generates a LinkedIn post draft
* 🧪 Creates quizzes and evaluates answers
* 💾 Stores and retrieves memory using embeddings
* 📊 Logs execution traces of the agent

All outputs are saved as structured Markdown files.

---

## 🧪 Example Flow

1. User defines a goal (e.g. “Learn RAG systems”)
2. Agent retrieves relevant past memory
3. Agent generates a weekly plan + tasks
4. Tasks are stored and tracked
5. User completes tasks and runs quiz
6. Results update learning state
7. Next plan adapts based on progress

---

## 📂 Repo Structure

```
agent/               # Agent logic (planner, tools, loop)
weekly_plans/        # Generated plans
tasks/               # Task tracking
posts/               # LinkedIn drafts
docs/                # Memory + notes
docs/learning_units/ # Generated learning units
data/                # memory vectors, traces, tasks
```

---

## 🛠 Tech Stack

* Python
* OpenAI / Ollama (LLMs)
* Embeddings + vector search (local)
* ReAct-style agent orchestration
* Streamlit UI

---

## ✔ What This Demonstrates

* Building an **end-to-end AI system**, not just models
* Working with **LLMs beyond prompting** (planning, memory, orchestration)
* Implementing **retrieval-based memory (RAG-like pattern)**
* Designing **agent workflows with tools and state**
* Creating **feedback loops (quiz → learning adaptation)**
* Structuring a system for **explainability via traces**

---

## ⚡ Status

Prototype complete and working locally.

* End-to-end flow implemented
* Memory + agent loop integrated
* UI available via Streamlit
* Offline/mock mode supported for testing

---

## ▶️ Run Locally

```bash
streamlit run app.py
```

### Providers

* OpenAI (default)
* Ollama (local)
* Mock mode (offline testing)

---

## 🔌 Configuration (optional)

```
LLM_PROVIDER=openai|ollama|mock
EMBEDDINGS_PROVIDER=openai|ollama|none
OPENAI_API_KEY=...
OLLAMA_MODEL=llama3.1:8b
```

---

## 📚 Learning Units & Quiz

* Learning units are generated and stored in `docs/learning_units/`
* Quiz system evaluates answers and updates learning state
* Memory is continuously updated for future planning

---

## ⚠️ Scope

This is a **local prototype**, not a production system.

Focus:

* system design
* agent workflows
* learning loop

Not included:

* authentication
* cloud deployment
* large-scale evaluation

---

## 🎯 Goal of This Project

To explore and demonstrate how to build **practical AI systems** that combine:

* planning
* memory
* interaction
* feedback

in a coherent workflow.
