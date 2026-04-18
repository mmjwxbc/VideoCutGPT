from fastapi import APIRouter
from pydantic import BaseModel
from app.services.multi_agent import MultiAgentSystem

router = APIRouter()
multi_agent_system = MultiAgentSystem()


class DiscussionRequest(BaseModel):
    topic: str
    requirements: str


@router.post("/discuss")
async def run_discussion(request: DiscussionRequest):
    """
    运行多Agent讨论
    """
    result = multi_agent_system.run_discussion(request.topic, request.requirements)
    return result
