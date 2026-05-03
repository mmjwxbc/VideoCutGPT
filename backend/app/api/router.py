from fastapi import APIRouter
from app.api.endpoints import caption

api_router = APIRouter()

# 注册各个模块的路由
api_router.include_router(caption.router, prefix="/caption", tags=["caption"])
