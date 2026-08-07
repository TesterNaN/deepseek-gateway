import json
import logging
from fastapi import APIRouter, Request, Depends, Response
from fastapi.responses import JSONResponse, StreamingResponse, PlainTextResponse
import httpx
from pydantic import BaseModel

from ..config import UPSTREAM_BASE_URL, DEFAULT_STREAM_FALLBACK
from ..database import get_upstream_key
from ..billing import get_model_pricing, calculate_cost, deduct_balance
from ..dependencies import authenticate_virtual_key, AuthInfo
from ..utils import try_acquire_slot, release_slot

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------- 自定义错误 ----------
class ProxyError(Exception):
    def __init__(self, message: str, status_code: int,
                 error_type: str = 'invalid_request_error',
                 code: str = None, as_json: bool = True):
        self.message = message
        self.status_code = status_code
        self.error_type = error_type
        self.code = code
        self.as_json = as_json
        super().__init__(message)

# ---------- 代理核心（最后注册） ----------
@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def proxy(path: str, request: Request, auth: AuthInfo = Depends(authenticate_virtual_key)):
    if not path:
        raise ProxyError('Not found', 404)

    upstream_key = await get_upstream_key()
    if not upstream_key:
        raise ProxyError('Upstream key not configured', 500)

    method = request.method
    data = None
    if method in ("POST", "PUT", "PATCH"):
        content_type = request.headers.get('content-type', '')
        if 'application/json' not in content_type:
            raise ProxyError('Only JSON supported', 415)
        try:
            data = await request.json()
        except Exception:
            raise ProxyError('Only JSON supported', 415)
        if data is None:
            raise ProxyError('Only JSON supported', 415)

    is_stream = bool(data.get('stream', False)) if isinstance(data, dict) else False
    model = data.get('model', '') if isinstance(data, dict) else ''

    # ---------- 并发控制（原子占用槽位） ----------
    if not try_acquire_slot(auth.virtual_key, auth.concurrency_enabled, auth.concurrency_limit):
        raise ProxyError(
            f'Too many concurrent requests, limit is {auth.concurrency_limit}',
            429, error_type='rate_limit_exceeded', code='concurrency_limit_exceeded'
        )

    target_url = f"{UPSTREAM_BASE_URL}/{path}"
    if request.url.query:
        target_url += f"?{request.url.query}"

    upstream_headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': f'Bearer {upstream_key}',
    }

    client: httpx.AsyncClient = request.app.state.http_client
    req = client.build_request(method, target_url, json=data, headers=upstream_headers)

    try:
        resp = await client.send(req, stream=is_stream)
    except httpx.TimeoutException:
        release_slot(auth.virtual_key)
        raise ProxyError('Upstream timeout', 504)
    except Exception as e:
        release_slot(auth.virtual_key)
        raise ProxyError(f'Upstream error: {str(e)}', 502)

    # 上游 401/402 统一屏蔽为 500
    if resp.status_code in (401, 402):
        try:
            await resp.aclose()
        except Exception:
            pass
        release_slot(auth.virtual_key)
        logger.warning(f"上游返回 {resp.status_code}，已屏蔽并返回 500 错误")
        raise ProxyError('服务器内部错误，请联系管理员处理', 500)

    pricing = await get_model_pricing()

    # ---------- 流式转发 ----------
    if is_stream:
        async def generate():
            final_usage = None
            try:
                async for line in resp.aiter_lines():
                    yield line + '\n'
                    if line.startswith('data:') and '[DONE]' not in line:
                        try:
                            raw = line[5:].strip()
                            if raw:
                                chunk = json.loads(raw)
                                if 'usage' in chunk and chunk['usage'] is not None:
                                    final_usage = chunk['usage']
                        except (json.JSONDecodeError, ValueError):
                            pass
            finally:
                try:
                    await resp.aclose()
                except Exception:
                    pass
                try:
                    if final_usage:
                        cost = calculate_cost(model, final_usage, pricing)
                        if cost > 0:
                            await deduct_balance(auth.virtual_key, cost, request)
                    else:
                        await deduct_balance(auth.virtual_key, DEFAULT_STREAM_FALLBACK, request)
                        logger.warning(f"流式未获取usage，按 {DEFAULT_STREAM_FALLBACK} 元扣费")
                except Exception:
                    logger.exception("流式结束后扣费失败")
                finally:
                    release_slot(auth.virtual_key)

        stream_headers = {"content-type": resp.headers.get("content-type", "text/event-stream")}
        return StreamingResponse(
            generate(),
            status_code=resp.status_code,
            headers=stream_headers,
        )

    # ---------- 非流式处理 ----------
    try:
        try:
            result = resp.json()
            if 'usage' in result:
                cost = calculate_cost(model, result['usage'], pricing)
                if cost > 0:
                    await deduct_balance(auth.virtual_key, cost, request)
            else:
                await deduct_balance(auth.virtual_key, DEFAULT_STREAM_FALLBACK, request)
            return JSONResponse(result, status_code=resp.status_code)
        except ValueError:
            await deduct_balance(auth.virtual_key, DEFAULT_STREAM_FALLBACK, request)
            content_type = resp.headers.get('content-type', 'text/plain')
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                media_type=content_type,
            )
    finally:
        try:
            await resp.aclose()
        except Exception:
            pass
        release_slot(auth.virtual_key)
