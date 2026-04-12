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
    "llama3.1:8b", 
    "qwen2.5-coder:7b", 
    "gemma4-e2b-it:latest", 
    "llama3.2:latest"
]

# Model registry — maps task type to model name
MODEL_MAP: dict[TaskType, str] = {
    "general":       "llama3.1:8b",
    "coding":        "qwen2.5-coder:7b",
    "quick":         "llama3.2:latest",
    "large_context": "gemma4-e2b-it:latest",
}

# Per-model context window — tuned for 8GB VRAM on RTX 4060
MODEL_CTX: dict[str, int] = {
    "llama3.1:8b":       4096,
    "qwen2.5-coder:7b":  4096,
    "gemma4-e2b-it:latest": 2048,
    "llama3.2:latest":   4096,
}

# Badges displayed in the user interface
TASK_BADGES: dict[TaskType, str] = {
    "general":       "🧠 GENERAL",
    "coding":        "💻 CODING",
    "quick":         "⚡ QUICK",
    "large_context": "📄 LARGE CONTEXT",
}
