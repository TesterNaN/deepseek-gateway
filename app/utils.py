import secrets
import string
from typing import Dict
from fastapi import Request

# ---------- 并发计数器（单进程内原子） ----------
active_requests: Dict[str, int] = {}

def try_acquire_slot(virtual_key: str, concurrency_enabled: bool, concurrency_limit: int) -> bool:
    current = active_requests.get(virtual_key, 0)
    if concurrency_enabled and concurrency_limit > 0 and current >= concurrency_limit:
        return False
    active_requests[virtual_key] = current + 1
    return True

def release_slot(virtual_key: str):
    current = active_requests.get(virtual_key, 0)
    if current > 1:
        active_requests[virtual_key] = current - 1
    else:
        active_requests.pop(virtual_key, None)

# ---------- 工具函数 ----------
def get_client_ip(request: Request = None) -> str:
    if request is None:
        return '未知IP'
    forwarded = request.headers.get('X-Forwarded-For')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.client.host if request.client else '未知IP'

def generate_random_password(length: int = 24) -> str:
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def generate_virtual_key() -> str:
    return "sk-" + secrets.token_hex(20)

def mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return key[:2] + "****" + key[-2:]

    prefix_len = 8
    suffix_len = 4
    hidden_len = len(key) - prefix_len - suffix_len
    if hidden_len < 1:
        hidden_len = 1

    return key[:prefix_len] + "*" * hidden_len + key[-suffix_len:]

