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
import json
import logging
from langchain_openai import ChatOpenAI

from config import (
    MODEL_MAP, 
    MODEL_CTX, 
    TaskType, 
    LM_STUDIO_API_URL, 
    EMBEDDING_MODEL_KEY, 
    LLM_SEARCH_KEYWORD, 
    LLM_IDENTIFIER
)

logger = logging.getLogger(__name__)


class ModelManager:
    """
    Singleton-style manager for LM Studio model lifecycle.
    Ensures only one LLM model is active at any time to preserve VRAM,
    while keeping the tiny embedding model loaded for RAG.
    """

    def __init__(self):
        self._current_model: str | None = None
        self._llm: ChatOpenAI | None = None

    def _get_loaded_models(self) -> list[dict]:
        try:
            flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            result = subprocess.run(
                ["lms", "ps", "--json"],
                capture_output=True,
                text=True,
                check=True,
                creationflags=flags
            )
            return json.loads(result.stdout)
        except Exception as e:
            logger.warning("Failed to check loaded models via 'lms ps --json': %s", e)
            return []

    def _resolve_model_key_and_path(self, search_term: str) -> tuple[str, str]:
        """Finds the modelKey and path of a downloaded model matching a search term."""
        try:
            flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            result = subprocess.run(
                ["lms", "ls", "--json"],
                capture_output=True,
                text=True,
                check=True,
                creationflags=flags
            )
            models = json.loads(result.stdout)
            for m in models:
                m_key = m.get("modelKey", "")
                m_path = m.get("path", "")
                if search_term.lower() in m_key.lower() or search_term.lower() in m_path.lower():
                    return m_key, m_path
        except Exception as e:
            logger.error("Failed to run 'lms ls --json': %s", e)
        raise RuntimeError(
            f"No local model matches search keyword '{search_term}' in LM Studio.\n"
            f"Please download it via LM Studio UI first."
        )

    def _ensure_embedding_loaded(self):
        """Ensure the embedding model is loaded since it's required for RAG."""
        loaded = self._get_loaded_models()
        is_embedding_loaded = any(
            m.get("identifier") == EMBEDDING_MODEL_KEY or 
            m.get("modelKey") == EMBEDDING_MODEL_KEY or
            EMBEDDING_MODEL_KEY in m.get("path", "")
            for m in loaded
        )
        if not is_embedding_loaded:
            logger.info("Loading embedding model: %s", EMBEDDING_MODEL_KEY)
            try:
                m_key, m_path = self._resolve_model_key_and_path(EMBEDDING_MODEL_KEY)
                flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                subprocess.run(
                    ["lms", "load", m_key, "--identifier", EMBEDDING_MODEL_KEY, "--yes"],
                    check=True,
                    creationflags=flags
                )
                logger.info("Embedding model loaded successfully.")
            except Exception as e:
                logger.error("Failed to load embedding model: %s", e)

    def switch_to(self, task_type: TaskType) -> "ModelManager":
        """
        Select the correct model for the given task type.
        Unloads any other running LLMs first to release VRAM.
        """
        target_model = MODEL_MAP.get(task_type, MODEL_MAP["general"])
        return self.switch_to_name(target_model)

    def switch_to_name(self, model_name: str) -> "ModelManager":
        """
        Directly switch to a model by name.
        Manages VRAM by unloading other LLMs.
        """
        self._ensure_embedding_loaded()

        loaded = self._get_loaded_models()
        is_target_loaded = False
        for m in loaded:
            if m.get("identifier") == model_name or m.get("modelKey") == model_name:
                is_target_loaded = True
                break

        if is_target_loaded:
            self._current_model = model_name
            self._llm = ChatOpenAI(
                base_url=LM_STUDIO_API_URL,
                api_key="lm-studio",
                model=model_name,
                temperature=0
            )
            return self

        for m in loaded:
            m_id = m.get("identifier")
            m_type = m.get("type", "")
            if m_id != EMBEDDING_MODEL_KEY and m_type != "embedding" and m_id is not None:
                logger.info("Unloading other LLM model to release VRAM: %s", m_id)
                try:
                    flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                    subprocess.run(["lms", "unload", m_id], check=True, creationflags=flags)
                except Exception as e:
                    logger.warning("Failed to unload model %s: %s", m_id, e)

        ctx = MODEL_CTX.get(model_name, 4096)
        search_term = LLM_SEARCH_KEYWORD if model_name == LLM_IDENTIFIER else model_name
        logger.info("Resolving model key/path for search term: %s", search_term)
        m_key, m_path = self._resolve_model_key_and_path(search_term)

        logger.info("Loading LLM model: %s (identifier=%s, context=%d)", m_path, model_name, ctx)
        try:
            flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            subprocess.run(
                ["lms", "load", m_key, "--identifier", model_name, "--context-length", str(ctx), "--yes"],
                check=True,
                creationflags=flags
            )
            logger.info("LLM model loaded successfully.")
        except Exception as e:
            raise RuntimeError(f"Failed to load model '{model_name}' in LM Studio: {e}")

        self._current_model = model_name
        self._llm = ChatOpenAI(
            base_url=LM_STUDIO_API_URL,
            api_key="lm-studio",
            model=model_name,
            temperature=0
        )
        return self

    def get_llm(self) -> ChatOpenAI:
        """Return the currently active LLM. Must call switch_to() first."""
        if self._llm is None:
            raise RuntimeError("No model loaded. Call switch_to() first.")
        return self._llm

    def get_model_name(self) -> str | None:
        return self._current_model

    def stop_current_model(self):
        """Public method to stop the currently running model and clear state."""
        if self._current_model:
            logger.info("Stopping/Unloading: %s", self._current_model)
            try:
                flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                subprocess.run(["lms", "unload", self._current_model], check=True, creationflags=flags)
            except Exception as e:
                logger.warning("Could not unload %s: %s", self._current_model, e)
            self._current_model = None
            self._llm = None
