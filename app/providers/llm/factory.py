"""Factory for creating LLM providers using DB-driven model selection."""
import os
import time
import logging
from typing import Optional

from app.providers.llm.base import LLMProvider

logger = logging.getLogger(__name__)

# Cache TTL in seconds
_CACHE_TTL = 60

# Cached provider and timestamp
_cached_provider: Optional[LLMProvider] = None
_cached_at: float = 0


class LLMProviderFactory:
    """Factory for creating LLM provider instances from DB configuration."""

    @staticmethod
    def get_default_provider() -> LLMProvider:
        """
        Get the active LLM provider based on DB configuration.

        Uses a 60-second cache to avoid hitting the DB on every call.
        Falls back to OPENROUTER_MODEL env var if DB has no models.

        Returns:
            LLMProvider instance
        """
        global _cached_provider, _cached_at

        now = time.time()
        if _cached_provider is not None and (now - _cached_at) < _CACHE_TTL:
            return _cached_provider

        # Query DB for the active model
        model_name = None
        try:
            from app.services.llm_model_service import get_current_active_model
            active_model = get_current_active_model()
            if active_model:
                model_name = active_model.model_name
                logger.info(f"Using DB-configured LLM model: {model_name}")
        except Exception as e:
            logger.warning(f"Could not query LLM model from DB: {e}")

        # Fallback to env var
        if not model_name:
            model_name = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")
            logger.info(f"Using fallback LLM model from env: {model_name}")

        from app.providers.llm.openrouter_provider import OpenRouterProvider
        _cached_provider = OpenRouterProvider(model=model_name)
        _cached_at = now

        logger.info(
            f"Initialized LLM provider: {_cached_provider.get_provider_name()} "
            f"({_cached_provider.get_model_name()})"
        )
        return _cached_provider

    @staticmethod
    def reset_provider():
        """Reset the cached provider (called after admin changes model/tier)."""
        global _cached_provider, _cached_at
        _cached_provider = None
        _cached_at = 0
        logger.info("LLM provider cache reset")
