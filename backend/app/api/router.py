from fastapi import APIRouter
from app.api.endpoints import caption, multi_agent, deep_research

api_router = APIRouter()

# 注册各个模块的路由
api_router.include_router(caption.router, prefix="/caption", tags=["caption"])
api_router.include_router(multi_agent.router, prefix="/multi-agent", tags=["multi-agent"])
api_router.include_router(deep_research.router, prefix="/deep-research", tags=["deep-research"])
