"""OpenRouter LLM provider."""
import os
import logging
from typing import Optional

from app.providers.llm.base import LLMProvider

logger = logging.getLogger(__name__)

# Environment variables
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterProvider(LLMProvider):
    """LLM provider using OpenRouter API (OpenAI-compatible)."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        """
        Initialize the OpenRouter provider.

        Args:
            api_key: OpenRouter API key (defaults to OPENROUTER_API_KEY env var)
            model: Model to use (defaults to OPENROUTER_MODEL env var)
        """
        self.api_key = api_key or OPENROUTER_API_KEY
        self.model = model or OPENROUTER_MODEL

    def get_provider_name(self) -> str:
        return "OpenRouter"

    def get_model_name(self) -> str:
        return self.model

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def generate(self, prompt: str) -> Optional[str]:
        """Generate a response using OpenRouter API."""
        if not self.is_configured():
            logger.error("OPENROUTER_API_KEY not configured")
            return None

        try:
            from openai import OpenAI

            client = OpenAI(
                base_url=OPENROUTER_BASE_URL,
                api_key=self.api_key,
            )

            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                temperature=0.7,
                max_tokens=2048,
            )

            if not response or not response.choices or not response.choices[0].message.content:
                logger.error("Empty response from OpenRouter")
                return None

            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"Error generating response from OpenRouter: {e}")
            return None
