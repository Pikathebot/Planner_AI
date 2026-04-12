"""
agent/classifier.py
Classifies a user goal into one of four task types to determine model selection.

Task types:
  "coding"        → qwen2.5-coder:7b   (coding-specific tasks)
  "quick"         → gemma4:e2b          (short/simple questions, fast answers)
  "large_context" → gemma4:e2b          (summarize, analyze, compare long content)
  "general"       → llama3.1:8b         (default planning and reasoning)
"""

import re
from config import TaskType

# ── Keyword sets ──────────────────────────────────────────────────────────────

CODING_KEYWORDS = {
    # Languages
    "python", "javascript", "typescript", "java", "c++", "rust", "golang",
    "php", "swift", "kotlin", "ruby", "scala", "haskell",
    # Frameworks & tools
    "fastapi", "flask", "django", "express", "nodejs", "react", "vue",
    "angular", "nextjs", "spring", "rails", "laravel",
    # Concepts
    "api", "rest api", "graphql", "websocket", "microservice",
    "algorithm", "data structure", "recursion", "regex",
    "unit test", "integration test", "tdd", "ci/cd", "pipeline",
    "docker", "kubernetes", "terraform", "nginx",
    "sql", "nosql", "mongodb", "postgres", "sqlite", "redis",
    "lambda function", "async", "concurrency", "threading",
    "web scraping", "scraper", "crawler",
    "machine learning", "neural network", "deep learning", "model training",
    "llm", "fine tuning", "fine-tuning", "embedding",
    # Explicitly technical actions
    "debug", "debugging", "refactor", "compile", "deploy an app",
    "write code", "write a script", "write a function", "write a program",
    "implement", "code", "script", "program",
}

# Quick = short factual / definitional questions → gemma4:e2b (fast)
QUICK_STARTERS = {
    "what is", "what are", "what does", "what do",
    "why is", "why are", "why does", "why do",
    "who is", "who are", "who was",
    "when is", "when was", "when did",
    "where is", "where are", "where was",
    "how does", "how do", "how is",
    "is it", "are there", "can i",
    "define", "explain what", "tell me what", "quickly explain",
    "briefly explain", "give me a quick",
}

QUICK_KEYWORDS = {
    "quickly", "briefly", "simple explanation", "in short", "tldr",
    "just explain", "just tell me", "what exactly", "simple overview",
}

LARGE_CONTEXT_KEYWORDS = {
    "analyze", "analysis", "summarize", "summary", "review",
    "compare", "comparison", "contrast", "evaluate", "assessment",
    "document", "pdf", "report", "research paper", "essay",
    "entire codebase", "full text", "repository overview",
    "multiple files", "project overview",
    "translate", "transcribe", "transcript",
    "long document", "large file",
}


def _matches_any(keywords: set, text: str) -> bool:
    """Whole-word/phrase match — avoids substring false positives."""
    for kw in keywords:
        pattern = r"\b" + re.escape(kw) + r"\b"
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def _is_quick_question(goal: str) -> bool:
    """
    Detect short, simple factual questions that gemma4:e2b can answer quickly.
    Criteria:
      - Starts with a known question phrase (what is, why does, etc.)
      - OR contains explicit quick/brief keywords
      - AND is reasonably short (≤ 15 words) to avoid classifying complex questions
    """
    goal_lower = goal.strip().lower()
    word_count = len(goal.split())

    # Check for quick keywords anywhere in the goal
    if _matches_any(QUICK_KEYWORDS, goal_lower):
        return True

    # Check if it starts with a quick starter phrase AND is short
    if word_count <= 15:
        for starter in QUICK_STARTERS:
            if goal_lower.startswith(starter):
                return True

    return False


def classify_task(goal: str) -> TaskType:
    """
    Classify the user's goal into a task type.

    Returns:
        "coding"        → use qwen2.5-coder:7b
        "quick"         → use gemma4:e2b  (fast, short answer)
        "large_context" → use gemma4:e2b  (large content processing)
        "general"       → use llama3.1:8b (default)
    """
    # Coding takes highest priority
    if _matches_any(CODING_KEYWORDS, goal):
        return "coding"

    # Quick factual questions → gemma4 for speed
    if _is_quick_question(goal):
        return "quick"

    # Large context / document tasks → gemma4 for capacity
    if _matches_any(LARGE_CONTEXT_KEYWORDS, goal):
        return "large_context"

    return "general"
