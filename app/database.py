import os
import sqlite3
import logging
from contextlib import asynccontextmanager

import aiosqlite

from .config import DATABASE

logger = logging.getLogger(__name__)

@asynccontextmanager
async def get_db():
    conn = await aiosqlite.connect(DATABASE)
    conn.row_factory = aiosqlite.Row
    try:
        await conn.execute("PRAGMA busy_timeout = 5000")
        yield conn
        await conn.commit()
    finally:
        await conn.close()

async def init_db():
    async with aiosqlite.connect(DATABASE) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.executescript('''
            CREATE TABLE IF NOT EXISTS keys (
                virtual_key TEXT PRIMARY KEY,
                tenant TEXT NOT NULL,
                balance REAL DEFAULT 0.0,
                total_recharged REAL DEFAULT 0.0,
                total_consumed REAL DEFAULT 0.0,
                concurrency_limit INTEGER DEFAULT 0,
                concurrency_enabled INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        await conn.commit()

    # 从环境变量导入上游 Key
    async with get_db() as conn:
        cursor = await conn.execute("SELECT value FROM config WHERE key = 'upstream_key'")
        row = await cursor.fetchone()
        if not row:
            env_key = os.environ.get("DEEPSEEK_UPSTREAM_KEY")
            if env_key:
                await conn.execute(
                    "INSERT INTO config (key, value) VALUES ('upstream_key', ?)",
                    (env_key,)
                )
                await conn.commit()
                logger.info("从环境变量导入上游 Key")

# ---------- 上游 Key 操作 ----------
async def get_upstream_key():
    async with get_db() as conn:
        cursor = await conn.execute("SELECT value FROM config WHERE key = 'upstream_key'")
        row = await cursor.fetchone()
        return row['value'] if row else None

async def set_upstream_key(new_key: str):
    async with get_db() as conn:
        await conn.execute(
            "INSERT OR REPLACE INTO config (key, value, updated_at) VALUES ('upstream_key', ?, CURRENT_TIMESTAMP)",
            (new_key,)
        )
        await conn.commit()
