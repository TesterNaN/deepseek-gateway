"""
DeepSeek API 中转站 完整功能测试脚本
=====================================
使用前请确保：
    1. 代理服务和管理服务已启动（python run.py）
    2. 管理员密码已知（首次启动控制台输出的临时密码，或修改后的密码）
    3. 已配置上游 API Key（管理面板或环境变量）

用法：
    # 交互输入密码
    python test_full.py

    # 或通过环境变量指定密码（适合自动化）
    set ADMIN_PASSWORD=your_password  && python test_full.py   # Windows
    ADMIN_PASSWORD=your_password python test_full.py           # Linux/Mac

可配置项（修改下方常量）：
    PROXY_BASE：代理服务地址（默认 http://localhost:5000）
    ADMIN_BASE：管理服务地址（默认 http://127.0.0.1:8000）
"""

import os
import sys
import requests
import secrets

# ---------- 配置区（可按需修改） ----------
PROXY_BASE = "http://localhost:5000"
ADMIN_BASE = "http://127.0.0.1:8000"

# 动态生成唯一测试 Key（避免与已有 Key 冲突）
TEST_VIRTUAL_KEY = "sk-test-" + secrets.token_hex(12)

# 测试使用的模型（确保上游支持）
TEST_MODEL = "deepseek-v4-flash"

# 管理员密码：优先从环境变量读取，否则交互输入
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

# ---------- 会话 ----------
session = requests.Session()


def log(name, passed, detail=""):
    print(f"[{'✅ PASS' if passed else '❌ FAIL'}] {name} {detail}")


def check_response(resp, expected_status=200, json_expected=True):
    if resp.status_code != expected_status:
        return False, f"状态码 {resp.status_code} (期望 {expected_status})"
    if json_expected:
        try:
            resp.json()
            return True, ""
        except:
            return False, "响应不是 JSON"
    return True, ""


# ---------- 测试模块 ----------
def test_login():
    print("\n--- 1. 登录 ---")

    resp = session.post(f"{ADMIN_BASE}/login",
                        data={"username": "admin", "password": ADMIN_PASSWORD},
                        allow_redirects=False)
    ok, detail = check_response(resp, expected_status=303, json_expected=False)
    log("管理员登录", ok, detail or "303 跳转")

    resp = session.get(f"{ADMIN_BASE}/login", allow_redirects=False)
    ok = resp.status_code in (302, 303, 307) and resp.headers.get("Location") == "/admin"
    log("已登录访问login跳转admin", ok, f"状态码 {resp.status_code}")

    tmp = requests.Session()
    resp = tmp.get(f"{ADMIN_BASE}/admin", allow_redirects=False)
    ok = resp.status_code in (302, 303, 307) and resp.headers.get("Location") == "/login"
    log("未登录访问admin跳转login", ok, f"状态码 {resp.status_code}")


def test_keys_api():
    print("\n--- 2. Key 管理 API ---")

    # 创建测试 Key（显式指定 virtual_key，确保后续操作使用同一 Key）
    resp = session.post(f"{ADMIN_BASE}/admin/keys",
                        json={
                            "virtual_key": TEST_VIRTUAL_KEY,
                            "tenant": "test_tenant",
                            "balance": 10.0
                        })
    ok, detail = check_response(resp, expected_status=201)
    log("创建Key", ok, detail or resp.json().get('virtual_key', ''))

    resp = session.get(f"{ADMIN_BASE}/admin/keys")
    keys = resp.json() if resp.status_code == 200 else []
    existed = any(k['virtual_key'] == TEST_VIRTUAL_KEY for k in keys)
    log("获取Key列表", resp.status_code == 200 and existed, f"共 {len(keys)} 个Key")

    resp = session.put(f"{ADMIN_BASE}/admin/keys/{TEST_VIRTUAL_KEY}",
                       json={"action": "recharge", "amount": 5.0})
    ok, detail = check_response(resp)
    log("充值Key", ok, detail or "增加5元")

    resp = session.put(f"{ADMIN_BASE}/admin/keys/{TEST_VIRTUAL_KEY}",
                       json={"action": "set_concurrency", "limit": 3, "enabled": True})
    ok, detail = check_response(resp)
    log("设置并发限制", ok, detail or "限制3并发")

    resp = session.get(f"{ADMIN_BASE}/admin/keys")
    for k in resp.json():
        if k['virtual_key'] == TEST_VIRTUAL_KEY:
            log("余额校验", k['balance'] >= 15, f"余额={k['balance']}")
            log("并发校验", k['concurrency_limit'] == 3 and k['concurrency_enabled'] == 1,
                f"limit={k['concurrency_limit']} enabled={k['concurrency_enabled']}")
            break


def test_pricing_api():
    print("\n--- 3. 定价管理 API ---")

    resp = session.get(f"{ADMIN_BASE}/admin/pricing")
    ok, detail = check_response(resp)
    data = resp.json() if ok else {}
    log("获取定价", ok, f"models={list(data.get('effective', {}).keys())}")

    resp = session.put(f"{ADMIN_BASE}/admin/pricing",
                       json={"models": {"test-model": {"input_hit": 0.1, "input_miss": 0.5, "output": 1.0}}})
    ok, detail = check_response(resp)
    log("修改定价", ok, "新增 test-model")

    resp = session.get(f"{ADMIN_BASE}/admin/pricing")
    ok = "test-model" in resp.json().get('effective', {})
    log("定价生效", ok, "")

    resp = session.delete(f"{ADMIN_BASE}/admin/pricing")
    ok, detail = check_response(resp)
    log("恢复默认定价", ok, detail)


def test_upstream_api():
    print("\n--- 4. 上游配置 API ---")

    resp = session.get(f"{ADMIN_BASE}/admin/upstream/key")
    ok, detail = check_response(resp)
    data = resp.json() if ok else {}
    log("获取上游Key", ok, f"exists={data.get('exists')} masked={data.get('masked')}")

    resp = session.get(f"{ADMIN_BASE}/admin/upstream/balance")
    log("查询上游余额", resp.status_code in (200, 400), f"状态 {resp.status_code}")


def test_background_api():
    print("\n--- 5. 背景配置 API ---")
    resp = session.get(f"{ADMIN_BASE}/admin/background")
    ok, detail = check_response(resp)
    data = resp.json() if ok else {}
    log("获取背景配置", ok, f"enabled={data.get('enabled')} url={data.get('url')}")


def test_proxy():
    print("\n--- 6. 代理功能 ---")
    headers = {"Authorization": f"Bearer {TEST_VIRTUAL_KEY}"}

    payload = {
        "model": TEST_MODEL,
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 5,
        "stream": False
    }
    try:
        resp = session.post(f"{PROXY_BASE}/chat/completions", json=payload, headers=headers)
        ok = resp.status_code == 200
        detail = f"content: {resp.json()['choices'][0]['message']['content'][:10]}" if ok else f"status {resp.status_code}"
        log("Chat非流式", ok, detail)
    except Exception as e:
        log("Chat非流式", False, str(e))

    payload_stream = {
        "model": TEST_MODEL,
        "messages": [{"role": "user", "content": "Tell a short word"}],
        "max_tokens": 20,
        "stream": True,
        "stream_options": {"include_usage": True}
    }
    try:
        resp = session.post(f"{PROXY_BASE}/chat/completions", json=payload_stream, headers=headers, stream=True)
        ok = resp.status_code == 200
        usage_found = False
        if ok:
            for line in resp.iter_lines(decode_unicode=True):
                if line and line.startswith('data:'):
                    raw = line[5:].strip()
                    if raw == '[DONE]':
                        break
                    try:
                        chunk = json.loads(raw)
                        if chunk.get('usage'):
                            usage_found = True
                    except:
                        pass
        log("Chat流式", ok and usage_found, "包含usage" if usage_found else "未找到usage")
    except Exception as e:
        log("Chat流式", False, str(e))

    try:
        resp = session.get(f"{PROXY_BASE}/models", headers=headers)
        ok = resp.status_code == 200
        log("模型列表", ok, f"count={len(resp.json().get('data', []))}")
    except Exception as e:
        log("模型列表", False, str(e))

    try:
        resp = session.get(f"{PROXY_BASE}/user/balance", headers=headers)
        ok = resp.status_code == 200 and resp.json().get('is_available') is True
        log("用户余额", ok, "")
    except Exception as e:
        log("用户余额", False, str(e))


def test_errors():
    print("\n--- 7. 错误场景 ---")
    resp = session.post(f"{PROXY_BASE}/chat/completions",
                        json={"model": TEST_MODEL, "messages": [{"role": "user", "content": "Hi"}]})
    ok = resp.status_code == 401 and resp.text.startswith("Authentication Fails")
    log("无认证", ok, f"status {resp.status_code}")

    resp = session.post(f"{PROXY_BASE}/chat/completions",
                        json={"model": TEST_MODEL, "messages": [{"role": "user", "content": "Hi"}]},
                        headers={"Authorization": "Bearer sk-invalid"})
    ok = resp.status_code == 401 and resp.json().get('error', {}).get('code') == 'invalid_request_error'
    log("无效Key", ok, f"status {resp.status_code}")

    session.put(f"{ADMIN_BASE}/admin/keys/{TEST_VIRTUAL_KEY}", json={"action": "set_balance", "amount": 0})
    resp = session.post(f"{PROXY_BASE}/chat/completions",
                        json={"model": TEST_MODEL, "messages": [{"role": "user", "content": "Hi"}]},
                        headers={"Authorization": f"Bearer {TEST_VIRTUAL_KEY}"})
    ok = resp.status_code == 402
    log("余额不足", ok, f"status {resp.status_code}")
    session.put(f"{ADMIN_BASE}/admin/keys/{TEST_VIRTUAL_KEY}", json={"action": "set_balance", "amount": 10.0})

    resp = session.post(f"{PROXY_BASE}/chat/completions",
                        data="not json",
                        headers={"Authorization": f"Bearer {TEST_VIRTUAL_KEY}"})
    ok = resp.status_code == 415
    log("非JSON", ok, f"status {resp.status_code}")


def cleanup():
    print("\n--- 8. 清理测试数据 ---")
    resp = session.delete(f"{ADMIN_BASE}/admin/keys/{TEST_VIRTUAL_KEY}")
    log("删除测试Key", resp.status_code == 200, f"status {resp.status_code}")


# ---------- 主流程 ----------
def main():
    print("=" * 60)
    print("DeepSeek 中转站完整功能测试")
    print("=" * 60)

    global ADMIN_PASSWORD
    if not ADMIN_PASSWORD:
        ADMIN_PASSWORD = input("请输入管理员密码：").strip()
        if not ADMIN_PASSWORD:
            print("未提供密码，测试终止")
            sys.exit(1)

    # 登录
    resp = session.post(f"{ADMIN_BASE}/login",
                        data={"username": "admin", "password": ADMIN_PASSWORD},
                        allow_redirects=False)
    if resp.status_code != 303:
        print(f"❌ 登录失败：{resp.status_code}")
        sys.exit(1)

    print(f"测试 Key: {TEST_VIRTUAL_KEY}\n")

    test_login()
    test_keys_api()
    test_pricing_api()
    test_upstream_api()
    test_background_api()
    test_proxy()
    test_errors()
    cleanup()

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
