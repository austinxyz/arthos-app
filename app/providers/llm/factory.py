"""Factory for creating LLM providers."""
import os
import logging
from typing import Optional

from app.providers.llm.base import LLMProvider

logger = logging.getLogger(__name__)

# Environment variable for selecting provider
# Options: "openrouter" (default), "gemini"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openrouter")


class LLMProviderFactory:
    """Factory for creating LLM provider instances."""

    _instance: Optional[LLMProvider] = None

    @staticmethod
    def get_provider(provider_name: Optional[str] = None) -> LLMProvider:
        """
        Get an LLM provider instance.

        Args:
            provider_name: Name of provider ('openrouter', 'gemini')
                          If None, uses LLM_PROVIDER env var (default: 'openrouter')

        Returns:
            LLMProvider instance

        Raises:
            ValueError: If provider name is unknown
        """
        if provider_name is None:
            provider_name = LLM_PROVIDER

        provider_name = provider_name.lower()

        if provider_name == "openrouter":
            from app.providers.llm.openrouter_provider import OpenRouterProvider
            return OpenRouterProvider()
        elif provider_name == "gemini":
            from app.providers.llm.gemini_provider import GeminiProvider
            return GeminiProvider()
        else:
            raise ValueError(f"Unknown LLM provider: {provider_name}")

    @staticmethod
    def get_default_provider() -> LLMProvider:
        """
        Get or create the default LLM provider instance (singleton pattern).

        Returns:
            Default LLMProvider instance
        """
        if LLMProviderFactory._instance is None:
            LLMProviderFactory._instance = LLMProviderFactory.get_provider()
            logger.info(
                f"Initialized LLM provider: {LLMProviderFactory._instance.get_provider_name()} "
                f"({LLMProviderFactory._instance.get_model_name()})"
            )
        return LLMProviderFactory._instance

    @staticmethod
    def reset_provider():
        """Reset the cached provider instance (useful for testing)."""
        LLMProviderFactory._instance = None
