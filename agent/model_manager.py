"""
agent/model_manager.py
Manages lifecycle of local Ollama models.

Spec requirement:
  - Only ONE model may be active at a time
  - Before switching, the current model must be stopped (releases VRAM)
  - Uses `ollama stop <model>` via subprocess

Context window tuned for RTX 4060 (8GB VRAM):
  llama3.1:8b      → 4096 tokens  (~4.9 GB base, 3.1 GB free — comfortable)
  qwen2.5-coder:7b → 4096 tokens  (~4.7 GB base, 3.3 GB free — comfortable)
  gemma4-e2b-it:latest       → 2048 tokens  (~7.2 GB base, 0.8 GB free — must limit)
"""

import subprocess
import urllib.request
import urllib.error
import json
import logging
from langchain_ollama import ChatOllama

from config import MODEL_MAP, MODEL_CTX, TaskType

logger = logging.getLogger(__name__)


class ModelManager:
    """
    Singleton-style manager for Ollama model lifecycle.
    Ensures only one model is active at any time.
    """

    def __init__(self):
        self._current_model: str | None = None
        self._llm: ChatOllama | None = None

    def switch_to(self, task_type: TaskType) -> "ModelManager":
        """
        Select the correct model for the given task type.
        Stops the currently running model first (if different).

        Args:
            task_type: "general", "coding", or "large_context"

        Returns:
            self (for chaining)
        """
        target_model = MODEL_MAP.get(task_type, MODEL_MAP["general"])

        if self._current_model == target_model:
            # Already on the right model — no switch needed
            return self

        self._ensure_model_available(target_model)

        # Stop the current model to release VRAM (spec requirement)
        if self._current_model is not None:
            self._stop_model(self._current_model)

        # Load the new model with the appropriate context window
        ctx = MODEL_CTX.get(target_model, 4096)
        logger.info("Loading: %s (num_ctx=%d)", target_model, ctx)
        self._current_model = target_model
        self._llm = ChatOllama(model=target_model, temperature=0, num_ctx=ctx)
        return self

    def switch_to_name(self, model_name: str) -> "ModelManager":
        """
        Directly switch to a model by name — used for manual user overrides.
        Bypasses the task_type → model_name lookup.
        """
        if self._current_model == model_name:
            return self
        self._ensure_model_available(model_name)

        if self._current_model is not None:
            self._stop_model(self._current_model)
        ctx = MODEL_CTX.get(model_name, 4096)
        logger.info("Loading (manual override): %s (num_ctx=%d)", model_name, ctx)
        self._current_model = model_name
        self._llm = ChatOllama(model=model_name, temperature=0, num_ctx=ctx)
        return self

    def get_llm(self) -> ChatOllama:
        """Return the currently active LLM. Must call switch_to() first."""
        if self._llm is None:
            raise RuntimeError("No model loaded. Call switch_to() first.")
        return self._llm

    def get_model_name(self) -> str | None:
        return self._current_model

    def stop_current_model(self):
        """Public method to stop the currently running model and clear state."""
        if self._current_model:
            self._stop_model(self._current_model)
            self._current_model = None
            self._llm = None

    def _stop_model(self, model_name: str):
        """Stop a running Ollama model to release VRAM via REST API."""
        logger.info("Stopping: %s", model_name)
        try:
            req = urllib.request.Request(
                "http://localhost:11434/api/generate",
                data=json.dumps({"model": model_name, "keep_alive": 0}).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                pass
        except (urllib.error.URLError, TimeoutError) as e:
            logger.warning("Could not stop %s via API: %s", model_name, e)

    def _ensure_model_available(self, model_name: str):
        """Verify the model is installed locally before trying to load it."""
        try:
            flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            result = subprocess.run(
                ["ollama", "list"], 
                capture_output=True, 
                text=True, 
                check=True,
                creationflags=flags
            )
            if model_name not in result.stdout:
                raise RuntimeError(
                    f"Model '{model_name}' is not installed locally.\n"
                    f"Please run: ollama pull {model_name}"
                )
        except FileNotFoundError:
            raise RuntimeError("Ollama is not installed or not in PATH.")
