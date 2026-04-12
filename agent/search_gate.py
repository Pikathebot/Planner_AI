"""
agent/search_gate.py
Decides whether the agent needs to perform a web search or can answer from internal knowledge.

Heuristics used:
  - Temporal signals ("latest", "2025", "2026", "current") → search needed
  - Very specific/niche topics → search needed
  - Common, well-known topics → no search needed
"""

TEMPORAL_KEYWORDS = {
    "latest", "newest", "recent", "today", "this year", "current",
    "2024", "2025", "2026", "updated", "new", "just released",
    "trending", "breaking", "now", "right now",
}

NICHE_SIGNALS = {
    "how to", "step by step", "tutorial", "guide", "best way",
    "specific", "exact", "price", "cost", "when", "where",
}

COMMON_TOPICS = {
    "saas", "startup", "machine learning", "web development",
    "project management", "data science", "mobile app", "marketing",
    "career", "resume", "interview", "business plan", "freelancing",
    "personal finance", "fitness", "productivity",
}


def needs_search(goal: str) -> bool:
    """
    Returns True if the goal likely requires a web search for accurate results.
    Returns False if internal reasoning is sufficient.

    Policy from spec:
      Use search when:
        - Information is uncertain
        - Topic is recent or evolving
        - Specific implementation details are required
      Do NOT use when:
        - Task is basic or well-known
        - Internal reasoning is sufficient
    """
    goal_lower = goal.lower()

    # Explicit temporal signals → always search
    for kw in TEMPORAL_KEYWORDS:
        if kw in goal_lower:
            return True

    # If topic is a very common/well-known domain → skip search
    for topic in COMMON_TOPICS:
        if topic in goal_lower:
            return False

    # Niche "how to" queries on unknown topics → search
    for signal in NICHE_SIGNALS:
        if signal in goal_lower:
            return True

    # Default: trust internal reasoning
    return False
