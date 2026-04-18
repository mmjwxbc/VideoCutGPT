from fastapi import APIRouter
from pydantic import BaseModel
from app.services.deep_research import DeepResearch

router = APIRouter()
deep_research = DeepResearch()


class ResearchRequest(BaseModel):
    product: str
    target_market: str


@router.post("/market")
async def research_market(request: ResearchRequest):
    """
    进行市场调研
    """
    result = deep_research.research_market(request.product, request.target_market)
    return result
