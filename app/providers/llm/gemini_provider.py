"""Google Gemini LLM provider."""
import os
import logging
from typing import Optional

from app.providers.llm.base import LLMProvider

logger = logging.getLogger(__name__)

# Environment variables
GOOGLE_AI_API_KEY = os.getenv("GOOGLE_AI_API_KEY")
GOOGLE_AI_MODEL = os.getenv("GOOGLE_AI_MODEL", "gemini-2.0-flash")


class GeminiProvider(LLMProvider):
    """LLM provider using Google Gemini API."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        """
        Initialize the Gemini provider.

        Args:
            api_key: Google AI API key (defaults to GOOGLE_AI_API_KEY env var)
            model: Model to use (defaults to GOOGLE_AI_MODEL env var)
        """
        self.api_key = api_key or GOOGLE_AI_API_KEY
        self.model = model or GOOGLE_AI_MODEL

    def get_provider_name(self) -> str:
        return "Gemini"

    def get_model_name(self) -> str:
        return self.model

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def generate(self, prompt: str) -> Optional[str]:
        """Generate a response using Google Gemini API."""
        if not self.is_configured():
            logger.error("GOOGLE_AI_API_KEY not configured")
            return None

        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.api_key)

            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.7,
                    max_output_tokens=2048,
                )
            )

            if not response or not response.text:
                logger.error("Empty response from Gemini")
                return None

            return response.text

        except Exception as e:
            logger.error(f"Error generating response from Gemini: {e}")
            return None
