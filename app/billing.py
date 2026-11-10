import json
import logging
import math
from copy import deepcopy
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from chinese_calendar import is_holiday

from .config import DEFAULT_PRICING, DEFAULT_PRICING_MODE, MODEL_ALIASES
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


BEIJING = timezone(timedelta(hours=8))


def get_pricing_period(at: datetime = None) -> str:
    """北京时间判断，周末即使调休补班也属于空闲时段。"""
    at = at or datetime.now(BEIJING)
    if at.tzinfo is None:
        raise ValueError("计费时间必须包含时区")
    local = at.astimezone(BEIJING)
    try:
        holiday = is_holiday(local.date())
    except NotImplementedError as exc:
        raise HTTPException(503, "节假日日历未覆盖当前年份，请升级 chinesecalendar") from exc
    minute = local.hour * 60 + local.minute
    peak = local.weekday() < 5 and not holiday and (
        540 <= minute < 720 or 840 <= minute < 1080
    )
    return "peak" if peak else "off_peak"


def with_aliases(pricing: dict) -> dict:
    result = deepcopy(pricing)
    for alias, canonical in MODEL_ALIASES.items():
        result.setdefault(alias, deepcopy(result[canonical]))
    return result


async def get_pricing_settings(at: datetime = None) -> dict:
    # 一次读取，避免请求过程中模式与价格来自不同版本。
    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT key, value FROM config WHERE key IN ('model_pricing', 'pricing_mode')"
        )
        values = {row['key']: row['value'] for row in await cursor.fetchall()}
    custom = json.loads(values.get('model_pricing', '{}'))
    mode = values.get('pricing_mode', DEFAULT_PRICING_MODE)
    merged = deepcopy(DEFAULT_PRICING)
    merged.update(custom)
    fixed = with_aliases(merged)
    peak = with_aliases(DEFAULT_PRICING)
    off_peak = {model: {key: value / 2 for key, value in prices.items()}
                for model, prices in peak.items()}
    period = get_pricing_period(at) if mode == 'peak_valley' else 'fixed'
    return {
        'mode': mode, 'custom': custom, 'fixed': fixed,
        'effective': fixed if mode == 'fixed' else (peak if period == 'peak' else off_peak),
        'period': period, 'peak': peak, 'off_peak': off_peak,
        'is_default': not custom and mode == DEFAULT_PRICING_MODE,
        'note': '价格单位为元/百万tokens；按请求开始时的北京时间锁定价格',
    }


async def get_model_pricing(at: datetime = None) -> dict:
    return (await get_pricing_settings(at))['effective']


async def set_custom_pricing(pricing: dict = None, mode: str = None) -> dict:
    """保存自定义定价，返回最终生效的定价表"""
    sanitized = {}
    if mode is not None and mode not in ('fixed', 'peak_valley'):
        raise ValueError('未知计费模式')
    for model, prices in (pricing or {}).items():
        if not isinstance(model, str) or not model.strip():
            continue
        cleaned = {}
        for key in ("input_hit", "input_miss", "output"):
            try:
                val = float(prices.get(key, 0))
            except (TypeError, ValueError) as exc:
                raise ValueError('单价必须为非负有限数字') from exc
            if not math.isfinite(val) or val < 0:
                raise ValueError('单价必须为非负有限数字')
            cleaned[key] = val
        sanitized[model.strip()] = cleaned

    async with get_db() as conn:
        if sanitized:
            await conn.execute(
                "INSERT OR REPLACE INTO config (key, value, updated_at) "
                "VALUES ('model_pricing', ?, CURRENT_TIMESTAMP)",
                (json.dumps(sanitized, ensure_ascii=False),)
            )
        elif pricing is not None:
            await conn.execute("DELETE FROM config WHERE key = 'model_pricing'")
        if mode is not None:
            await conn.execute(
                "INSERT OR REPLACE INTO config (key, value, updated_at) "
                "VALUES ('pricing_mode', ?, CURRENT_TIMESTAMP)", (mode,)
            )
        await conn.commit()

    return await get_model_pricing()


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
