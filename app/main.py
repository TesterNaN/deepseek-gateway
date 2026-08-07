import secrets
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from .database import init_db
from .dependencies import init_admin_password
from .api.proxy import ProxyError
from .api.auth import router as auth_router
from .api.admin import router as admin_router
from .api.proxy import router as proxy_router

logging.getLogger('uvicorn.access').setLevel(logging.WARNING)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------- 共享 HTTP 客户端 ----------
_http_client = None

async def get_shared_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=10.0),
            limits=httpx.Limits(max_connections=200, max_keepalive_connections=50),
            follow_redirects=True,
        )
    return _http_client

# ---------- 通用中间件 ----------
def add_common_middleware(app: FastAPI):
    app.add_middleware(
        SessionMiddleware,
        secret_key=secrets.token_hex(32),
        max_age=31 * 24 * 3600,
        same_site="lax",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

def add_common_exception_handlers(app: FastAPI):
    @app.exception_handler(ProxyError)
    async def proxy_error_handler(request: Request, exc: ProxyError):
        if not exc.as_json:
            from fastapi.responses import PlainTextResponse
            return PlainTextResponse(exc.message, status_code=exc.status_code)
        return JSONResponse(
            {
                "error": {
                    "message": exc.message,
                    "type": exc.error_type,
                    "param": None,
                    "code": exc.code
                }
            },
            status_code=exc.status_code,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception(f"未处理的异常: {exc}")
        return JSONResponse(
            {
                "error": {
                    "message": "服务器内部错误，请联系管理员处理",
                    "type": "server_error",
                    "param": None,
                    "code": None
                }
            },
            status_code=500,
        )

# ---------- 创建代理服务（只开放转发 API） ----------
@asynccontextmanager
async def proxy_lifespan(app: FastAPI):
    app.state.http_client = await get_shared_http_client()
    logger.info("代理服务已启动")
    try:
        yield
    finally:
        pass  # 共享客户端由主进程统一关闭

def create_proxy_app() -> FastAPI:
    app = FastAPI(
        title="DeepSeek 代理",
        lifespan=proxy_lifespan,
        docs_url=None, redoc_url=None, openapi_url=None,
    )
    add_common_middleware(app)
    add_common_exception_handlers(app)

    # 代理服务专有路由
    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/user/balance")
    async def custom_balance():
        return {
            "is_available": True,
            "balance_infos": [
                {
                    "currency": "CNY",
                    "total_balance": "0.00",
                    "granted_balance": "0.00",
                    "topped_up_balance": "0.00"
                }
            ]
        }

    # 代理核心（最后注册，捕获所有剩余路径）
    app.include_router(proxy_router)
    return app

# ---------- 创建管理服务（只开放管理接口） ----------
@asynccontextmanager
async def admin_lifespan(app: FastAPI):
    await init_db()
    await init_admin_password(app)
    app.state.http_client = await get_shared_http_client()
    logger.info("管理服务已启动")
    try:
        yield
    finally:
        pass

def create_admin_app() -> FastAPI:
    app = FastAPI(
        title="DeepSeek 中转站管理",
        lifespan=admin_lifespan,
        docs_url=None, redoc_url=None, openapi_url=None,
    )
    add_common_middleware(app)
    add_common_exception_handlers(app)

    # 访问管理面板根路径直接跳转到 /admin
    @app.get("/")
    async def admin_root():
        return RedirectResponse("/admin")

    # 管理面板静态资源
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    # 登录 / 管理页面 / 管理 API
    app.include_router(auth_router)
    app.include_router(admin_router)
    return app


proxy_app = create_proxy_app()
admin_app = create_admin_app()
