# Local AI Planning Agent — Specification

## Objective

Build an AI agent that:

* Understands a user’s goal
* Determines required knowledge
* Identifies missing skills
* Searches for relevant information when needed
* Produces a clear, structured execution plan

---

# Available Models

The system has access to:

* `llama3.1:8b` → Primary reasoning and planning
* `qwen2.5-coder:7b` → Coding and technical tasks
* `gemma4:e2b` → Fast reasoning and large context handling

---

# Model Usage Strategy

The agent must dynamically select models based on task type.

## Default

Use `llama3.1:8b` for:

* Planning
* General reasoning
* Structured output generation

## Technical or Coding Tasks

Use `qwen2.5-coder:7b`

## Large Context or Speed Requirements

Use `gemma4:e2b`

---

# Model Switching Policy

When switching between models, the agent must:

1. Stop or terminate the currently running model instance
2. Release resources (especially GPU/VRAM)
3. Initialize and run the new model

Failure to do this may cause:

* Memory conflicts
* Performance degradation
* Incorrect outputs

The agent must ensure that only one model is actively running at a time unless explicitly designed otherwise.

---

# Agent Behavior

## Core Principle

The agent must not immediately produce an answer.

It must follow a reasoning loop:

```id="m7q1zp"
Understand → Analyze → Decide → Act → Refine → Answer
```

---

# Reasoning Workflow

## Step 1 — Understand Goal

* Parse the user’s intent
* Identify:

  * Domain (coding, business, learning, etc.)
  * Complexity level

---

## Step 2 — Identify Requirements

Determine:

* Required skills
* Required tools
* Dependencies

---

## Step 3 — Detect Knowledge Gaps

Evaluate:

* What the user likely does not know
* What must be learned first

---

## Step 4 — Decide on Search

```id="v8f2yx"
IF knowledge is insufficient
    → use search tool
ELSE
    → proceed without search
```

---

## Step 5 — Use Tools (if needed)

When using search:

* Generate specific and actionable queries
* Avoid vague queries

### Example

```id="b1p9kc"
Bad: "AI chatbot"
Good: "steps to build AI chatbot using local LLM 2026"
```

---

## Step 6 — Analyze Results

* Extract relevant and actionable information
* Discard irrelevant or noisy data

---

## Step 7 — Generate Plan

The agent must produce a structured and logically ordered plan.

---

# Output Format (Strict)

The output must always follow:

```id="t5x2qd"
Prerequisites:
- ...

Learning Path:
- ...

Step-by-step Plan:
1.
2.
3.
```

---

# Output Rules

* Be concise but complete
* Avoid vague statements
* Ensure all steps are actionable
* Maintain logical sequencing
* Do not include extra commentary outside the defined structure

---

# Intelligence Guidelines

## The agent should:

* Think step-by-step internally
* Use tools only when necessary
* Prefer clarity over verbosity
* Adapt to goal complexity

## The agent should not:

* Skip reasoning steps
* Produce generic answers
* Ignore missing knowledge
* Overuse tools unnecessarily

---

# Tool Usage Policy

## Search Tool

Use when:

* Information is uncertain
* Topic is recent or evolving
* Specific implementation details are required

Do not use when:

* The task is basic or well-known
* Internal reasoning is sufficient

---

# Planning Strategy

The generated plan must follow a logical progression:

## 1. Foundations

* Core concepts and prerequisites

## 2. Setup Phase

* Tools, environment, and initial configuration

## 3. Execution Phase

* Step-by-step implementation

## 4. Improvement Phase

* Optimization and scaling

---

# Example Behavior

## Input

```id="w9k3az"
I want to build a SaaS product
```

## Output

```id="c2n8rl"
Prerequisites:
- Basic programming knowledge
- Understanding of web architecture
- Basics of databases

Learning Path:
- Learn backend development
- Learn frontend basics
- Understand SaaS business models

Step-by-step Plan:
1. Define product idea and target users
2. Choose tech stack
3. Build MVP backend
4. Develop frontend
5. Deploy application
6. Gather feedback and iterate
```

---

# RAG Decision

## Current Status: Not Required

Reason:

* The system focuses on dynamic planning
* Web search provides sufficient external knowledge
* No persistent memory is required at this stage

---

## When to Introduce RAG

RAG should be added only if:

* Persistent memory is needed
* The system must use custom documents (PDFs, notes, etc.)
* Personalization becomes necessary

---

# Future Expansion

## Level 4 Features

* Multi-agent system:

  * Planner agent
  * Research agent
  * Executor agent

* Memory system (RAG)

* File ingestion capabilities

* User interface integration

---

# Key Design Philosophy

The system should function as a reasoning-driven assistant rather than a static chatbot.

---

# Success Criteria

The agent is considered successful if:

* It decides when to use tools appropriately
* It produces structured and actionable plans
* It adapts to different types of goals
* It avoids generic or shallow responses

---

# End of Specification
