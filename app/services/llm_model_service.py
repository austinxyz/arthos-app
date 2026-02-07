"""Service for managing LLM models and active tier from the database."""
import logging
from datetime import datetime
from typing import List, Optional

from sqlmodel import Session, select

from app.database import engine
from app.models.llm_model import LLMModel
from app.models.app_settings import AppSettings

logger = logging.getLogger(__name__)

# Default seed data
DEFAULT_MODELS = [
    {"model_name": "google/gemini-2.5-flash-preview-05-20", "tier": "free", "is_active": True},
    {"model_name": "anthropic/claude-sonnet-4", "tier": "paid", "is_active": True},
]
DEFAULT_TIER = "free"


def get_all_models() -> List[LLMModel]:
    """Return all LLM models ordered by tier then name."""
    with Session(engine) as session:
        statement = select(LLMModel).order_by(LLMModel.tier, LLMModel.model_name)
        return list(session.exec(statement).all())


def get_active_tier() -> str:
    """Read active tier from app_settings (default 'free')."""
    with Session(engine) as session:
        setting = session.get(AppSettings, "llm_active_tier")
        return setting.value if setting else DEFAULT_TIER


def set_active_tier(tier: str) -> None:
    """Update the active tier in app_settings."""
    if tier not in ("free", "paid"):
        raise ValueError(f"Invalid tier: {tier}")

    with Session(engine) as session:
        setting = session.get(AppSettings, "llm_active_tier")
        if setting:
            setting.value = tier
            setting.updated_at = datetime.utcnow()
        else:
            setting = AppSettings(key="llm_active_tier", value=tier)
        session.add(setting)
        session.commit()
    logger.info(f"Active LLM tier set to: {tier}")


def get_current_active_model() -> Optional[LLMModel]:
    """Get the active model for the current active tier."""
    tier = get_active_tier()
    with Session(engine) as session:
        statement = select(LLMModel).where(
            LLMModel.tier == tier,
            LLMModel.is_active == True
        )
        return session.exec(statement).first()


def add_model(model_name: str, tier: str) -> LLMModel:
    """Add a new LLM model. Auto-activates if it's the first for its tier."""
    if tier not in ("free", "paid"):
        raise ValueError(f"Invalid tier: {tier}")

    with Session(engine) as session:
        # Check if any model exists for this tier
        existing = session.exec(
            select(LLMModel).where(LLMModel.tier == tier)
        ).all()
        is_first = len(existing) == 0

        model = LLMModel(
            model_name=model_name,
            tier=tier,
            is_active=is_first,
        )
        session.add(model)
        session.commit()
        session.refresh(model)
        logger.info(f"Added LLM model: {model_name} (tier={tier}, active={is_first})")
        return model


def activate_model(model_id: int) -> LLMModel:
    """Activate a model, deactivating the current active model for the same tier."""
    with Session(engine) as session:
        model = session.get(LLMModel, model_id)
        if not model:
            raise ValueError(f"Model {model_id} not found")

        # Deactivate current active model for this tier
        current_active = session.exec(
            select(LLMModel).where(
                LLMModel.tier == model.tier,
                LLMModel.is_active == True
            )
        ).all()
        for m in current_active:
            m.is_active = False
            session.add(m)

        # Activate the requested model
        model.is_active = True
        session.add(model)
        session.commit()
        session.refresh(model)
        logger.info(f"Activated LLM model: {model.model_name} (tier={model.tier})")
        return model


def delete_model(model_id: int) -> bool:
    """Delete a model. Prevents deleting the active model for a tier."""
    with Session(engine) as session:
        model = session.get(LLMModel, model_id)
        if not model:
            raise ValueError(f"Model {model_id} not found")
        if model.is_active:
            raise ValueError("Cannot delete the active model. Activate another model first.")

        session.delete(model)
        session.commit()
        logger.info(f"Deleted LLM model: {model.model_name}")
        return True


def seed_default_models() -> None:
    """Seed default models and tier setting if tables are empty."""
    with Session(engine) as session:
        existing = session.exec(select(LLMModel)).first()
        if existing:
            return  # Already seeded

        for data in DEFAULT_MODELS:
            model = LLMModel(**data)
            session.add(model)

        # Set default tier
        tier_setting = session.get(AppSettings, "llm_active_tier")
        if not tier_setting:
            session.add(AppSettings(key="llm_active_tier", value=DEFAULT_TIER))

        session.commit()
        logger.info("Seeded default LLM models and tier setting")
