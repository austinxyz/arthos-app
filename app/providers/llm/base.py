"""Base class for LLM providers."""
from abc import ABC, abstractmethod
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def get_provider_name(self) -> str:
        """Return the name of this provider."""
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """Return the model being used."""
        pass

    @abstractmethod
    def is_configured(self) -> bool:
        """Check if the provider is properly configured (API key set, etc.)."""
        pass

    @abstractmethod
    def generate(self, prompt: str) -> Optional[str]:
        """
        Generate a response from the LLM.

        Args:
            prompt: The prompt to send to the LLM

        Returns:
            The generated text response, or None on failure
        """
        pass
