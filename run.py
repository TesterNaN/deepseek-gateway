import json
import os
import asyncio
import uvicorn

from app.main import proxy_app, admin_app

DEFAULT_CONFIG = {
    "proxy_host": "0.0.0.0",
    "proxy_port": 5000,
    "admin_host": "127.0.0.1",
    "admin_port": 8000,
    "background": {
        "enabled": True,
        "url": "https://t.alcy.cc/pc"
    }
}

def ensure_config():
    """如果 config.json 不存在，则创建默认配置"""
    if not os.path.exists("config.json"):
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=4)
        print("⚠️  未检测到 config.json，已生成默认配置文件。")
        print("   请检查并修改 config.json 中的端口等配置。")

def load_config():
    ensure_config()
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)

async def main():
    config = load_config()

    proxy_config = uvicorn.Config(
        proxy_app,
        host=config.get("proxy_host", "0.0.0.0"),
        port=config.get("proxy_port", 5000),
        access_log=False,
        log_level="warning",
    )
    admin_config = uvicorn.Config(
        admin_app,
        host=config.get("admin_host", "127.0.0.1"),
        port=config.get("admin_port", 8000),
        access_log=False,
        log_level="warning",
    )

    proxy_server = uvicorn.Server(proxy_config)
    admin_server = uvicorn.Server(admin_config)

    print("=" * 60)
    print("DeepSeek 中转站已启动")
    print(f"   代理 API:   http://{proxy_config.host}:{proxy_config.port}")
    print(f"   管理面板:   http://{admin_config.host}:{admin_config.port}")
    print("=" * 60)

    await asyncio.gather(proxy_server.serve(), admin_server.serve())

if __name__ == "__main__":
    asyncio.run(main())
