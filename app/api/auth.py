import json
import logging
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from werkzeug.security import check_password_hash, generate_password_hash

from ..dependencies import require_admin
from ..database import get_db
from ..utils import get_client_ip

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

class ChangePasswordModel(BaseModel):
    old_password: str
    new_password: str

def load_background_config():
    """从 config.json 读取背景配置"""
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
        bg = config.get("background", {})
        return bg.get("enabled", False), bg.get("url", "https://t.alcy.cc/pc")
    except Exception:
        return False, ""

def render_login(request, error=None):
    bg_enabled, bg_url = load_background_config()
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": error,
        "bg_enabled": bg_enabled,
        "bg_url": bg_url
    })

@router.get("/login", response_class=HTMLResponse)
async def login_page_get(request: Request):
    # 已登录用户访问登录页，直接跳转到管理面板
    if request.session.get('admin_logged_in'):
        return RedirectResponse('/admin', status_code=303)
    return render_login(request)

@router.post("/login", response_class=HTMLResponse)
async def login_page_post(request: Request):
    # 已登录用户提交登录表单，直接跳转到管理面板
    if request.session.get('admin_logged_in'):
        return RedirectResponse('/admin', status_code=303)

    form = await request.form()
    username = form.get('username', '')
    password = form.get('password', '')

    if username != 'admin':
        return render_login(request, error="用户名或密码错误")

    password_hash = getattr(request.app.state, 'admin_password_hash', None)
    if not password_hash:
        return render_login(request, error="管理员密码未初始化，请联系管理员")

    if await run_in_threadpool(check_password_hash, password_hash, password):
        request.session['admin_logged_in'] = True
        return RedirectResponse('/admin', status_code=303)

    return render_login(request, error="用户名或密码错误")

@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse('/login')

@router.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request):
    if not request.session.get('admin_logged_in'):
        return RedirectResponse('/login')
    return templates.TemplateResponse("admin.html", {"request": request})

@router.post("/admin/change_password", dependencies=[Depends(require_admin)])
async def change_password(request: Request, body: ChangePasswordModel):
    old_password = body.old_password
    new_password = body.new_password

    if not old_password or not new_password or len(new_password) < 6:
        from .proxy import ProxyError
        raise ProxyError('旧密码和新密码（至少6位）为必填项', 400)

    current_hash = getattr(request.app.state, 'admin_password_hash', None)
    if not current_hash:
        from .proxy import ProxyError
        raise ProxyError('管理员密码未初始化', 500)

    if not await run_in_threadpool(check_password_hash, current_hash, old_password):
        from .proxy import ProxyError
        raise ProxyError('旧密码错误', 403)

    new_hash = await run_in_threadpool(generate_password_hash, new_password)

    async with get_db() as conn:
        await conn.execute(
            "INSERT OR REPLACE INTO config (key, value, updated_at) "
            "VALUES ('admin_password_hash', ?, CURRENT_TIMESTAMP)",
            (new_hash,)
        )
        await conn.commit()

    request.app.state.admin_password_hash = new_hash
    request.app.state.admin_password_mode = 'persistent'

    logger.info(f"[IP: {get_client_ip(request)}] 管理员密码已修改并持久化")
    return {"status": "ok", "message": "密码修改成功，已持久化（重启后仍然有效）"}
