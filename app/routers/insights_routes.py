"""
Stock insights and LLM model management API endpoints.
"""
from fastapi import APIRouter, Request, HTTPException, Query, Path as FPath
from pydantic import BaseModel
from starlette.templating import Jinja2Templates
from pathlib import Path as PathLib
from app.utils.route_helpers import _require_admin


router = APIRouter()

# Set up templates directory
templates_dir = PathLib(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


# Stock Insights API Endpoints
@router.get("/v1/stock/{ticker}/insights")
async def get_stock_insights(
    request: Request,
    ticker: str = FPath(...),
    refresh: bool = Query(False, description="Force refresh insights from LLM")
):
    """
    Get LLM-generated insights for a stock.

    Returns AI-generated comprehensive investment analysis covering strategic narrative,
    fundamentals, debt/cash flow, price action, future scenarios, and investment verdict.
    Insights are cached for 24 hours. Use refresh=true to force a fresh fetch.

    Args:
        request: Request object
        ticker: Stock ticker symbol
        refresh: If true, force refresh from LLM regardless of cache

    Returns:
        JSON response with insights data containing 'analysis' markdown text
    """
    from app.services import insights_service

    try:
        result = insights_service.get_insights(ticker, force_refresh=refresh)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching insights: {str(e)}")


# LLM Model Management API Endpoints
class LLMModelCreate(BaseModel):
    model_name: str
    tier: str


@router.get("/v1/llm-models")
async def list_llm_models(request: Request):
    """List all LLM models (admin-only)."""
    _require_admin(request)
    from app.services import llm_model_service

    models = llm_model_service.get_all_models()
    current_model = llm_model_service.get_current_active_model()

    return {
        "models": [
            {
                "id": m.id,
                "model_name": m.model_name,
                "tier": m.tier,
                "is_active": m.is_active,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in models
        ],
        "current_model": current_model.model_name if current_model else None,
    }


@router.post("/v1/llm-models")
async def create_llm_model(request: Request, body: LLMModelCreate):
    """Add a new LLM model (admin-only)."""
    _require_admin(request)
    from app.services import llm_model_service

    try:
        model = llm_model_service.add_model(body.model_name, body.tier)
        return {
            "id": model.id,
            "model_name": model.model_name,
            "tier": model.tier,
            "is_active": model.is_active,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/v1/llm-models/{model_id}/activate")
async def activate_llm_model(request: Request, model_id: int):
    """Activate an LLM model and reset provider cache (admin-only)."""
    _require_admin(request)
    from app.services import llm_model_service
    from app.providers.llm import LLMProviderFactory

    try:
        model = llm_model_service.activate_model(model_id)
        LLMProviderFactory.reset_provider()
        return {
            "id": model.id,
            "model_name": model.model_name,
            "tier": model.tier,
            "is_active": model.is_active,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/v1/llm-models/{model_id}")
async def delete_llm_model(request: Request, model_id: int):
    """Delete an LLM model (admin-only). Cannot delete the active model."""
    _require_admin(request)
    from app.services import llm_model_service

    try:
        llm_model_service.delete_model(model_id)
        return {"message": "Model deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/debug/llm-models")
async def debug_llm_models_page(request: Request):
    """
    Debug page for managing LLM models.

    Returns:
        HTML page with LLM model management UI
    """
    from app.services import llm_model_service

    models = llm_model_service.get_all_models()
    current_model = llm_model_service.get_current_active_model()

    return templates.TemplateResponse("debug_llm_models.html", {
        "request": request,
        "models": models,
        "current_model": current_model,
    })
