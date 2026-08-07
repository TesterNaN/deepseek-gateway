import logging
from fastapi import Request, HTTPException, Depends

from werkzeug.security import generate_password_hash

from .database import get_db
from .utils import generate_random_password

logger = logging.getLogger(__name__)

# ---------- 管理员密码初始化 ----------
async def init_admin_password(app):
    async with get_db() as conn:
        cursor = await conn.execute("SELECT value FROM config WHERE key = 'admin_password_hash'")
        row = await cursor.fetchone()

    if row:
        app.state.admin_password_hash = row['value']
        app.state.admin_password_mode = 'persistent'
        logger.info("管理员密码已持久化")
    else:
        temp_password = generate_random_password(24)
        app.state.admin_password_hash = generate_password_hash(temp_password)
        app.state.admin_password_mode = 'temporary'
        print("\n" + "=" * 60)
        print("管理员账户（临时密码，仅本次运行有效）")
        print(f"   用户名: admin")
        print(f"   密码:   {temp_password}")
        print("   提示: 此密码未保存，下次启动会重新生成")
        print("   如需固定密码，请在登录后通过管理面板修改")
        print("=" * 60 + "\n")

# ---------- 虚拟 Key 认证 ----------
class AuthInfo:
    def __init__(self, virtual_key: str, balance: float,
                 concurrency_enabled: bool, concurrency_limit: int):
        self.virtual_key = virtual_key
        self.balance = balance
        self.concurrency_enabled = concurrency_enabled
        self.concurrency_limit = concurrency_limit

async def authenticate_virtual_key(request: Request) -> AuthInfo:
    from .api.proxy import ProxyError  # 延迟导入避免循环

    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        raise ProxyError(
            'Authentication Fails (governor)',
            401, as_json=False
        )
    virtual_key = auth[len('Bearer '):].strip()

    async with get_db() as conn:
        cursor = await conn.execute(
            "SELECT virtual_key, balance, concurrency_limit, concurrency_enabled "
            "FROM keys WHERE virtual_key = ?",
            (virtual_key,)
        )
        row = await cursor.fetchone()

    if row is None:
        raise ProxyError(
            'Authentication Fails (governor)',
            401, error_type='authentication_error', code='invalid_request_error'
        )
    if row['balance'] <= 0:
        raise ProxyError(
            'Insufficient balance',
            402, error_type='insufficient_balance', code='insufficient_balance'
        )
    return AuthInfo(
        virtual_key=row['virtual_key'],
        balance=row['balance'],
        concurrency_enabled=bool(row['concurrency_enabled']),
        concurrency_limit=row['concurrency_limit'],
    )

# ---------- 管理员鉴权 ----------
async def require_admin(request: Request):
    if not request.session.get('admin_logged_in'):
        raise HTTPException(status_code=401, detail='请先登录管理员账户')
