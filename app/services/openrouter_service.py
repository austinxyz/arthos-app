"""Service for interacting with OpenRouter API."""
import os
import logging
from typing import List, Dict, Optional
import requests

logger = logging.getLogger(__name__)

OPENROUTER_API_URL = "https://openrouter.ai/api/v1"


def get_available_models() -> List[Dict[str, any]]:
    """
    Fetch available models from OpenRouter API.

    Returns:
        List of model dictionaries with id, name, pricing info, etc.
    """
    try:
        response = requests.get(
            f"{OPENROUTER_API_URL}/models",
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        models = data.get("data", [])

        # Enrich with pricing tier (free vs paid)
        enriched_models = []
        for model in models:
            pricing = model.get("pricing", {})
            prompt_price = float(pricing.get("prompt", "0"))
            completion_price = float(pricing.get("completion", "0"))

            # Consider it free if both prompt and completion are 0
            is_free = prompt_price == 0 and completion_price == 0

            enriched_models.append({
                "id": model.get("id"),
                "name": model.get("name", model.get("id")),
                "description": model.get("description", ""),
                "context_length": model.get("context_length", 0),
                "pricing": {
                    "prompt": prompt_price,
                    "completion": completion_price,
                },
                "tier": "Free" if is_free else "Paid",
                "is_free": is_free,
            })

        # Sort: Free models first, then by name
        enriched_models.sort(key=lambda m: (not m["is_free"], m["name"]))

        logger.info(f"Fetched {len(enriched_models)} models from OpenRouter")
        return enriched_models

    except Exception as e:
        logger.error(f"Error fetching OpenRouter models: {e}")
        return []


def test_prompt_with_model(model_id: str, prompt: str) -> Dict[str, any]:
    """
    Test a prompt with a specific OpenRouter model.

    Args:
        model_id: The OpenRouter model ID (e.g., "anthropic/claude-3.5-sonnet")
        prompt: The prompt to test

    Returns:
        Dictionary with success status, response text, and metadata
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return {
            "success": False,
            "error": "OPENROUTER_API_KEY not configured",
            "response": None,
        }

    try:
        from openai import OpenAI

        client = OpenAI(
            base_url=OPENROUTER_API_URL,
            api_key=api_key,
        )

        response = client.chat.completions.create(
            model=model_id,
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
            return {
                "success": False,
                "error": "Empty response from OpenRouter",
                "response": None,
            }

        content = response.choices[0].message.content
        usage = response.usage

        return {
            "success": True,
            "response": content,
            "model": model_id,
            "usage": {
                "prompt_tokens": usage.prompt_tokens if usage else 0,
                "completion_tokens": usage.completion_tokens if usage else 0,
                "total_tokens": usage.total_tokens if usage else 0,
            },
            "error": None,
        }

    except Exception as e:
        logger.error(f"Error testing prompt with model {model_id}: {e}")
        return {
            "success": False,
            "error": str(e),
            "response": None,
        }
