"""Factory for the chat model. The provider is chosen with environment variables."""

import os

from langchain_core.language_models import BaseChatModel

DEFAULT_ANTHROPIC_MODEL = "claude-opus-5-5"
DEFAULT_OLLAMA_MODEL = "qwen2.5-coder:7b"


def get_llm() -> BaseChatModel:
    """Return the chat model configured by LLM_PROVIDER (anthropic, ollama or fake)."""
    provider = os.getenv("LLM_PROVIDER", "anthropic").lower()

    if provider == "fake":
        # Deterministic double for tests and CI. Never use it for real reviews.
        from agent.testing import FakeLLM

        return FakeLLM()

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=os.getenv("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "4096")),
        )

    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        )

    raise ValueError(f"Unknown LLM_PROVIDER: {provider}")
