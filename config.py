"""
config.py
Centralized configuration for the Planner Agent application.
"""
from typing import Literal

# Type definition for supported tasks
TaskType = Literal["general", "coding", "quick", "large_context"]

# UI Choices for Gradio
AUTO_CHOICE = "🤖 Auto (recommended)"
MODEL_OPTIONS = [
    AUTO_CHOICE, 
    "gemma-4-12b",
    "qwen2.5-coder-1.5b-instruct",
]

# Model registry — maps task type to model name
MODEL_MAP: dict[TaskType, str] = {
    "general":       "gemma-4-12b",
    "coding":        "gemma-4-12b",
    "quick":         "qwen2.5-coder-1.5b-instruct",
    "large_context": "gemma-4-12b",
}

# Per-model context window — tuned for 8GB VRAM on RTX 4060
MODEL_CTX: dict[str, int] = {
    "gemma-4-12b":                 4096,
    "qwen2.5-coder-1.5b-instruct": 4096,
}

# LM Studio Server Configuration
LM_STUDIO_API_URL = "http://localhost:1234/v1"
EMBEDDING_MODEL_KEY = "text-embedding-nomic-embed-text-v1.5"
LLM_SEARCH_KEYWORD = "gemma-4"
LLM_IDENTIFIER = "gemma-4-12b"

# Badges displayed in the user interface
TASK_BADGES: dict[TaskType, str] = {
    "general":       "🧠 GENERAL",
    "coding":        "💻 CODING",
    "quick":         "⚡ QUICK",
    "large_context": "📄 LARGE CONTEXT",
}
