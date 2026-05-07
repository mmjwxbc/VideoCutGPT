from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse
from app.api.endpoints import caption

api_router = APIRouter()


@api_router.get("/", include_in_schema=False)
async def api_root(
    cf_access_message: str | None = Query(default=None, alias="__cf_access_message")
):
    if cf_access_message == "logged_out":
        return RedirectResponse(url="/api/access/complete", status_code=307)
    return {"message": "电商出海助手API服务运行中"}


@api_router.get("/access/complete", include_in_schema=False)
async def access_login_complete():
    return RedirectResponse(url="/", status_code=307)

# 注册各个模块的路由
api_router.include_router(caption.router, prefix="/caption", tags=["caption"])
