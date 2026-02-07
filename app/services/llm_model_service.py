"""Service for managing LLM models from the database."""
import logging
from typing import List, Optional

from sqlmodel import Session, select

from app.database import engine
from app.models.llm_model import LLMModel

logger = logging.getLogger(__name__)

# Default seed data - single active model
DEFAULT_MODELS = [
    {"model_name": "google/gemini-2.5-flash", "tier": "paid", "is_active": True},
]


def get_all_models() -> List[LLMModel]:
    """Return all LLM models ordered by tier then name."""
    with Session(engine) as session:
        statement = select(LLMModel).order_by(LLMModel.tier, LLMModel.model_name)
        return list(session.exec(statement).all())


def get_current_active_model() -> Optional[LLMModel]:
    """Get the single active model."""
    with Session(engine) as session:
        statement = select(LLMModel).where(LLMModel.is_active == True)
        return session.exec(statement).first()


def add_model(model_name: str, tier: str) -> LLMModel:
    """Add a new LLM model. Never auto-activates; use activate_model() to make it default."""
    if tier not in ("free", "paid"):
        raise ValueError(f"Invalid tier: {tier}")

    with Session(engine) as session:
        model = LLMModel(
            model_name=model_name,
            tier=tier,
            is_active=False,
        )
        session.add(model)
        session.commit()
        session.refresh(model)
        logger.info(f"Added LLM model: {model_name} (tier={tier})")
        return model


def activate_model(model_id: int) -> LLMModel:
    """Activate a model as the single default, deactivating all others."""
    with Session(engine) as session:
        model = session.get(LLMModel, model_id)
        if not model:
            raise ValueError(f"Model {model_id} not found")

        # Deactivate ALL models
        all_active = session.exec(
            select(LLMModel).where(LLMModel.is_active == True)
        ).all()
        for m in all_active:
            m.is_active = False
            session.add(m)

        # Activate the requested model
        model.is_active = True
        session.add(model)
        session.commit()
        session.refresh(model)
        logger.info(f"Activated LLM model: {model.model_name}")
        return model


def delete_model(model_id: int) -> bool:
    """Delete a model. Prevents deleting the active model."""
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
    """Seed default models if tables are empty."""
    with Session(engine) as session:
        existing = session.exec(select(LLMModel)).first()
        if existing:
            return  # Already seeded

        for data in DEFAULT_MODELS:
            model = LLMModel(**data)
            session.add(model)

        session.commit()
        logger.info("Seeded default LLM models")
