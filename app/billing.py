import json
import logging
from copy import deepcopy

from fastapi import Request

from .config import DEFAULT_PRICING
from .database import get_db
from .utils import get_client_ip

logger = logging.getLogger(__name__)

# ---------- 定价操作 ----------
async def get_custom_pricing() -> dict:
    """获取用户自定义的定价（未配置则返回空 dict）"""
    try:
        async with get_db() as conn:
            cursor = await conn.execute(
                "SELECT value FROM config WHERE key = 'model_pricing'"
            )
            row = await cursor.fetchone()
        if row:
            custom = json.loads(row['value'])
            if isinstance(custom, dict):
                return {k: v for k, v in custom.items() if isinstance(v, dict)}
    except Exception as e:
        logger.error(f"读取自定义定价异常: {e}")
    return {}


async def get_model_pricing() -> dict:
    """获取最终生效的定价表（自定义覆盖默认）"""
    custom = await get_custom_pricing()
    merged = deepcopy(DEFAULT_PRICING)
    merged.update(custom)
    return merged


async def set_custom_pricing(pricing: dict) -> dict:
    """保存自定义定价，返回最终生效的定价表"""
    sanitized = {}
    for model, prices in pricing.items():
        if not isinstance(model, str) or not model.strip():
            continue
        cleaned = {}
        for key in ("input_hit", "input_miss", "output"):
            try:
                val = float(prices.get(key, 0))
            except (TypeError, ValueError):
                val = 0.0
            cleaned[key] = max(val, 0.0)
        sanitized[model.strip()] = cleaned

    async with get_db() as conn:
        if sanitized:
            await conn.execute(
                "INSERT OR REPLACE INTO config (key, value, updated_at) "
                "VALUES ('model_pricing', ?, CURRENT_TIMESTAMP)",
                (json.dumps(sanitized, ensure_ascii=False),)
            )
        else:
            await conn.execute("DELETE FROM config WHERE key = 'model_pricing'")
        await conn.commit()

    merged = deepcopy(DEFAULT_PRICING)
    merged.update(sanitized)
    return merged


# ---------- 计费 ----------
def calculate_cost(model: str, usage: dict, pricing: dict) -> float:
    """根据模型和 usage 计算费用（元）"""
    if model not in pricing:
        return 0.0
    prices = pricing[model]
    prompt_tokens = usage.get('prompt_tokens', 0)
    completion_tokens = usage.get('completion_tokens', 0)
    hit_tokens = usage.get('prompt_cache_hit_tokens', 0)
    miss_tokens = usage.get('prompt_cache_miss_tokens', prompt_tokens - hit_tokens)

    cost = 0.0
    cost += miss_tokens * float(prices.get('input_miss', 0)) / 1_000_000
    cost += hit_tokens * float(prices.get('input_hit', 0)) / 1_000_000
    cost += completion_tokens * float(prices.get('output', 0)) / 1_000_000
    return cost


async def deduct_balance(virtual_key: str, amount: float, request: Request = None) -> bool:
    """原子扣费（防止余额变为负数）"""
    if amount <= 0:
        return True
    try:
        async with get_db() as conn:
            cursor = await conn.execute(
                "UPDATE keys SET balance = balance - ?, total_consumed = total_consumed + ?, "
                "updated_at = CURRENT_TIMESTAMP "
                "WHERE virtual_key = ? AND balance >= ?",
                (amount, amount, virtual_key, amount)
            )
            changed = cursor.rowcount
            await conn.commit()
    except Exception as e:
        logger.error(f"扣费失败: {e}")
        return False

    if changed == 0:
        logger.warning(f"[IP: {get_client_ip(request)}] 虚拟Key {virtual_key} 余额不足，无法扣费 {amount:.6f} 元")
        return False

    logger.info(f"[IP: {get_client_ip(request)}] 虚拟Key {virtual_key} 扣费 {amount:.6f} 元")
    return True
