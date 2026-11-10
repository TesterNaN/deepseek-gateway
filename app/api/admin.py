import sqlite3
import json
import logging
from copy import deepcopy

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse  # 👈 关键缺失导入
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Literal

from ..dependencies import require_admin
from ..database import get_db, get_upstream_key, set_upstream_key
from ..billing import get_pricing_settings, set_custom_pricing
from ..config import DEFAULT_CONCURRENCY_LIMIT, DEFAULT_CONCURRENCY_ENABLED, DEFAULT_PRICING
from ..utils import generate_virtual_key, mask_key, get_client_ip

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------- Pydantic 模型 ----------
class KeyCreate(BaseModel):
    virtual_key: Optional[str] = None
    tenant: str = 'default'
    balance: float = 0.0

class KeyUpdate(BaseModel):
    action: str
    amount: float = 0.0
    limit: int = 0
    enabled: bool = False

class UpstreamKeyUpdate(BaseModel):
    key: str

class ModelPrice(BaseModel):
    model_config = ConfigDict(extra='forbid')
    input_hit: float = Field(ge=0, allow_inf_nan=False)
    input_miss: float = Field(ge=0, allow_inf_nan=False)
    output: float = Field(ge=0, allow_inf_nan=False)

class PricingUpdate(BaseModel):
    mode: Optional[Literal['fixed', 'peak_valley']] = None
    models: Optional[Dict[str, ModelPrice]] = None

# ---------- 认证状态 ----------
@router.get("/admin/auth/status", dependencies=[Depends(require_admin)])
async def admin_auth_status(request: Request):
    mode = getattr(request.app.state, 'admin_password_mode', 'temporary')
    return {
        "password_mode": mode,
        "message": "已持久化" if mode == 'persistent' else "临时密码，仅本次运行有效，修改后即持久化"
    }

# ---------- 背景配置 ----------
@router.get("/admin/background", dependencies=[Depends(require_admin)])
async def get_background_config():
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
    except FileNotFoundError:
        config = {}
    bg = config.get("background", {})
    return {
        "enabled": bg.get("enabled", False),
        "url": bg.get("url", "https://t.alcy.cc/pc")
    }

# ---------- Key 管理 ----------
@router.get("/admin/keys", dependencies=[Depends(require_admin)])
async def admin_list_keys():
    async with get_db() as conn:
        cursor = await conn.execute("SELECT * FROM keys ORDER BY created_at DESC")
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]

@router.post("/admin/keys", status_code=201, dependencies=[Depends(require_admin)])
async def admin_add_key(request: Request, body: KeyCreate):
    from .proxy import ProxyError
    virtual_key = body.virtual_key or generate_virtual_key()
    if not virtual_key.startswith("sk-"):
        raise ProxyError('Virtual key must start with "sk-"', 400)

    try:
        async with get_db() as conn:
            await conn.execute(
                "INSERT INTO keys (virtual_key, tenant, balance, concurrency_limit, concurrency_enabled) "
                "VALUES (?, ?, ?, ?, ?)",
                (virtual_key, body.tenant, body.balance,
                 DEFAULT_CONCURRENCY_LIMIT,
                 1 if DEFAULT_CONCURRENCY_ENABLED else 0)
            )
            await conn.commit()
    except sqlite3.IntegrityError:
        raise ProxyError('Key already exists', 400)

    logger.info(f"[IP: {get_client_ip(request)}] 新增虚拟Key {virtual_key}，租户 {body.tenant}，初始余额 {body.balance}")
    return {"virtual_key": virtual_key, "tenant": body.tenant, "balance": body.balance}

@router.put("/admin/keys/{virtual_key}", dependencies=[Depends(require_admin)])
async def admin_update_key(request: Request, virtual_key: str, body: KeyUpdate):
    from .proxy import ProxyError
    ip = get_client_ip(request)
    async with get_db() as conn:
        if body.action == 'recharge':
            cursor = await conn.execute(
                "UPDATE keys SET balance = balance + ?, total_recharged = total_recharged + ?, "
                "updated_at = CURRENT_TIMESTAMP WHERE virtual_key = ?",
                (body.amount, body.amount, virtual_key)
            )
            logger.info(f"[IP: {ip}] 虚拟Key {virtual_key} 充值 {body.amount} 元")
        elif body.action == 'set_balance':
            cursor = await conn.execute(
                "UPDATE keys SET balance = ?, updated_at = CURRENT_TIMESTAMP WHERE virtual_key = ?",
                (body.amount, virtual_key)
            )
            logger.info(f"[IP: {ip}] 虚拟Key {virtual_key} 余额被设置为 {body.amount} 元")
        elif body.action == 'set_concurrency':
            limit = body.limit
            enabled = 1 if body.enabled else 0
            cursor = await conn.execute(
                "UPDATE keys SET concurrency_limit = ?, concurrency_enabled = ?, "
                "updated_at = CURRENT_TIMESTAMP WHERE virtual_key = ?",
                (limit, enabled, virtual_key)
            )
            logger.info(f"[IP: {ip}] 虚拟Key {virtual_key} 并发限制修改为 {limit}，启用状态: {bool(enabled)}")
        else:
            raise ProxyError('action must be "recharge", "set_balance" or "set_concurrency"', 400)

        changed = cursor.rowcount
        await conn.commit()

    if changed == 0:
        raise ProxyError('Key not found', 404)
    return {"status": "ok"}

@router.delete("/admin/keys/{virtual_key}", dependencies=[Depends(require_admin)])
async def admin_delete_key(request: Request, virtual_key: str):
    from .proxy import ProxyError
    async with get_db() as conn:
        cursor = await conn.execute("DELETE FROM keys WHERE virtual_key = ?", (virtual_key,))
        changed = cursor.rowcount
        await conn.commit()

    if changed == 0:
        raise ProxyError('Key not found', 404)
    logger.info(f"[IP: {get_client_ip(request)}] 虚拟Key {virtual_key} 已被删除")
    return {"status": "deleted"}

# ---------- 上游 Key ----------
@router.get("/admin/upstream/key", dependencies=[Depends(require_admin)])
async def admin_get_upstream_key():
    key = await get_upstream_key()
    if not key:
        return {"masked": "", "exists": False}
    return {"masked": mask_key(key), "exists": True}

@router.post("/admin/upstream/key", dependencies=[Depends(require_admin)])
async def admin_set_upstream_key(request: Request, body: UpstreamKeyUpdate):
    new_key = body.key
    if not new_key:
        from .proxy import ProxyError
        raise ProxyError('Key required', 400)
    await set_upstream_key(new_key)
    logger.info(f"[IP: {get_client_ip(request)}] 上游 API Key 已更新")
    return {"status": "ok"}

@router.get("/admin/upstream/balance", dependencies=[Depends(require_admin)])
async def admin_upstream_balance(request: Request):
    from .proxy import ProxyError
    key = await get_upstream_key()
    if not key:
        raise ProxyError('No upstream key configured', 400)

    client = request.app.state.http_client
    try:
        resp = await client.get(
            'https://api.deepseek.com/user/balance',
            headers={'Authorization': f'Bearer {key}'}
        )
    except Exception as e:
        raise ProxyError(str(e), 500)

    if resp.status_code != 200:
        try:
            return JSONResponse(resp.json(), status_code=resp.status_code)
        except Exception:
            raise ProxyError(f'Upstream API error: {resp.text}', resp.status_code)
    return JSONResponse(resp.json())  # 现在正常返回

# ---------- 模型定价 ----------
@router.get("/admin/pricing", dependencies=[Depends(require_admin)])
async def admin_get_pricing():
    return await get_pricing_settings()

@router.put("/admin/pricing", dependencies=[Depends(require_admin)])
async def admin_set_pricing(request: Request, body: PricingUpdate):
    models = None if body.models is None else {k: v.model_dump() for k, v in body.models.items()}
    await set_custom_pricing(models, body.mode)
    logger.info(f"[IP: {get_client_ip(request)}] 模型计费配置已更新")
    return {"status": "ok", **await get_pricing_settings()}

@router.delete("/admin/pricing", dependencies=[Depends(require_admin)])
async def admin_reset_pricing(request: Request):
    await set_custom_pricing({}, 'fixed')
    logger.info(f"[IP: {get_client_ip(request)}] 模型定价已恢复默认")
    return {"status": "ok", **await get_pricing_settings()}
