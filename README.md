# DeepSeek API 中转站 / 分发平台

一个开箱即用的 **DeepSeek API 分发网关**，让你可以安全、可控、可计费地向他人分发 API Key，同时隐藏真正的上游密钥。

如果你正在开发一款内置 LLM 功能的软件、游戏、Bot 或团队内部工具，需要让多个用户/玩家/成员共享 DeepSeek 能力，这个项目就是为你准备的。

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104%2B-brightgreen)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## 🤔 它解决什么问题？

| 场景 | 没有中转站 | 使用本中转站 |
|---|---|---|
| 你的软件内置 LLM 功能 | 把真实 API Key 塞进客户端，**极易被盗** | 分发虚拟 Key，被盗也无风险 |
| 多个用户共用同一个账号 | 无法区分用量，无法限制 | 每 Key 独立余额 + 并发限制 |
| 用户超量调用 | 无法控制，账单失控 | 余额扣光自动拒绝请求 |
| 想按不同用户/群组收费 | 做不到 | 自定义模型单价，按 token 计费 |
| 管理多个应用 | 混乱 | 按租户（tenant）隔离管理 |

---

## ✨ 核心特性

### 🔐 安全分发，不暴露上游 Key
- 真正的上游 Key 只存在服务器端，管理面板中仅显示打码
- 对外只暴露虚拟 Key（`sk-` 开头），即使泄露也无法访问你的 DeepSeek 账户

### 💰 按量计费，余额可控
- 每次请求按实际 token 消耗 × 模型单价自动扣费
- 余额不足自动拒绝（HTTP 402）
- 支持充值、手动设置余额、查看累计消费

### 🧾 自定义模型定价
- 可为每个模型单独设置：缓存命中输入 / 缓存未命中输入 / 输出 三个维度的价格
- 即时生效，无需重启服务

### 🚦 并发限制
- 为每个 Key 单独设置最大并发请求数
- 防止单个用户滥用资源，保障服务质量

### 🧑‍🤝‍🧑 多租户支持
- 每个虚拟 Key 可绑定一个租户（tenant）
- 适用于多个应用 / 多个团队 / 多个玩家群体

### 🎛️ 独立管理面板
- 代理服务与管理服务**分离端口**运行
- MD3 风格界面，深色/浅色自动跟随系统，可选动态壁纸背景

---

## 🎯 适用场景

- 🎮 **游戏内置 AI 对话**：给每个玩家分配独立 Key，限额免费/付费
- 🤖 **Bot / 插件分发**：让用户用自己的额度，而不是共享你的
- 🏢 **团队内部工具**：按部门/成员分配预算，用量透明
- 📱 **App 内 AI 功能**：后端中转，保护服务密钥不被逆向提取
- 🛒 **二次销售 API**：自定义定价，自己做上游

---

## 🚀 快速开始

### 1. 安装

```bash
git clone https://github.com/TesterNaN/deepseek-gateway.git
cd deepseek-gateway
pip install -r requirements.txt
```

### 2. 首次启动（自动生成配置）

```bash
python run.py
```

首次运行会自动创建 `config.json`：

```json
{
    "proxy_host": "0.0.0.0",
    "proxy_port": 5000,
    "admin_host": "127.0.0.1",
    "admin_port": 8000,
    "background": {
        "enabled": true,
        "url": "https://t.alcy.cc/pc"
    }
}
```

同时会在控制台输出一个**临时管理员密码**。

### 3. 配置上游 Key

方式一（环境变量）：

```bash
DEEPSEEK_UPSTREAM_KEY=sk-你的真实key python run.py
```

方式二（管理面板）：进入管理面板 → 上游配置 → 填写保存。

### 4. 登录管理面板

打开 `http://127.0.0.1:8000`，用户名 `admin`，输入控制台临时密码。登录后建议立即修改密码（保存后永久有效）。

### 5. 创建并分发虚拟 Key

在管理面板「虚拟密钥管理」中：

1. 点击 **添加新 Key**
2. 填写租户（如玩家 ID / 应用名）和初始余额
3. 生成 `sk-...` 虚拟 Key，复制给用户/客户端

### 6. 用户如何使用？

用户只需把 `http://你的服务器:5000` 当作 DeepSeek API 的 Base URL，换用自己的虚拟 Key：

```bash
curl http://你的服务器:5000/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-分发出去的虚拟key" \
  -d '{
    "model": "deepseek-chat",
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": false
  }'
```

支持 OpenAI 兼容的接口路径：

| 路径 | 功能 |
|---|---|
| `/chat/completions` | 对话补全 |
| `/responses` | Responses API |
| `/beta/completions` | FIM 补全 |
| `/models` | 模型列表 |
| `/user/balance` | 余额查询 |

> 所有非管理路径都会被自动转发到 `https://api.deepseek.com`，客户端无感知。

---

## 🔌 端口配置说明

本项目将「业务端口」与「管理端口」分离，确保安全性和灵活性。

| 配置项 | 默认值 | 作用 |
|---|---|---|
| `proxy_host` | `0.0.0.0` | 代理服务监听地址 |
| `proxy_port` | `5000` | **业务端口**，客户端请求的入口 |
| `admin_host` | `127.0.0.1` | 管理服务监听地址 |
| `admin_port` | `8000` | **管理端口**，管理面板/管理 API 的入口 |

**修改步骤：**

1. 编辑 `config.json`，例如：

```json
{
    "proxy_host": "0.0.0.0",
    "proxy_port": 8080,
    "admin_host": "0.0.0.0",
    "admin_port": 9000,
    "background": {
        "enabled": true,
        "url": "https://t.alcy.cc/pc"
    }
}
```

2. 保存后**重启服务**生效：

```bash
python run.py
```

**注意事项：**

- `proxy_port` 是客户端（用户/游戏/软件）调用 DeepSeek API 时使用的**业务入口**，需要对外暴露
- `admin_port` 是管理面板和管理 API 的入口，**建议仅绑定 `127.0.0.1`**（本机访问），不要暴露到公网
- 如果修改端口后无法访问，请检查防火墙/安全组是否放行了对应端口

---

## 🎨 随机背景设置

管理面板支持**动态随机背景图片**，配置位于 `config.json` 的 `background` 字段：

```json
{
    "background": {
        "enabled": true,
        "url": "https://t.alcy.cc/pc"
    }
}
```

| 字段 | 说明 |
|---|---|
| `enabled` | 是否启用随机背景。`false` 时使用默认纯色背景 |
| `url` | 随机图片 API 地址，支持任何返回图片的重定向服务 |

**使用说明：**

- 将 `enabled` 设为 `true` 后，管理面板和登录页会每次加载时随机展示一张壁纸
- 卡片区域使用高斯模糊（`backdrop-filter`）半透明效果，背景图片被柔和虚化，不影响文字可读性
- 更换图片 API 只需修改 `url` 字段，无需重启服务（重新登录或刷新后生效）
- 如果你想用 Unsplash、Bing 每日壁纸等任意图源，填上对应的图片 URL 即可

> 提示：`https://t.alcy.cc/pc` 是一个免费的随机电脑壁纸 API。如果你有更稳定的图源，也可以替换。

---

## 🧪 功能测试脚本

项目附带完整测试脚本 `test_full.py`，覆盖登录、Key 管理、定价、上游配置、背景、代理功能及错误场景。

```bash
# 交互输入密码
python test_full.py

# 或通过环境变量指定密码（适合自动化）
set ADMIN_PASSWORD=your_password && python test_full.py   # Windows
ADMIN_PASSWORD=your_password python test_full.py           # Linux/Mac
```

> 测试会自动创建动态测试 Key（`sk-test-...`），结束后自动删除，不会影响现有数据。测试代理功能需要已配置上游 API Key。

---

## 🔌 管理 API 文档（供二次开发 / 对接付费）

除了图形化管理面板，本项目提供完整的 **HTTP 管理 API**，你可以基于它自行开发用户中心、页面自动开通、用量查询等系统。

> **注意**：调用管理 API 必须先通过 `POST /login` 获取管理员会话，且只能通过管理端口（默认 8000）访问。所有管理 API 返回 JSON。

### 认证方式（获取会话）

```
POST /login
Content-Type: application/x-www-form-urlencoded

username=admin&password=你的管理员密码
```

成功后服务器会设置会话 Cookie，后续请求携带该 Cookie 即可访问所有管理接口。

---

### 1. 虚拟 Key 管理接口

#### 获取所有虚拟 Key

```
GET /admin/keys
```

**响应示例：**

```json
[
    {
        "virtual_key": "sk-3e5efe0e154e9aba27c50a16ad1f691e83f2bea2",
        "tenant": "player_001",
        "balance": 8.5,
        "total_recharged": 20.0,
        "total_consumed": 11.5,
        "concurrency_limit": 5,
        "concurrency_enabled": 1,
        "created_at": "2025-01-01 12:00:00",
        "updated_at": "2025-01-01 12:30:00"
    }
]
```

#### 创建虚拟 Key

```
POST /admin/keys
Content-Type: application/json
```

```json
{
    "tenant": "player_001",
    "balance": 10.0
}
```

| 参数 | 必填 | 说明 |
|---|---|---|
| `virtual_key` | 否 | 留空则自动生成 `sk-` 开头 Key |
| `tenant` | 否 | 租户标识，默认 `"default"` |
| `balance` | 否 | 初始余额，默认 `0` |

成功返回 `201` + Key 信息。

#### 修改虚拟 Key（充值 / 设置余额 / 并发限制）

```
PUT /admin/keys/{virtual_key}
Content-Type: application/json
```

**① 充值（对接付费系统核心接口）：**

```json
{ "action": "recharge", "amount": 10.0 }
```

**② 直接设置余额（谨慎操作）：**

```json
{ "action": "set_balance", "amount": 20.0 }
```

**③ 设置并发限制：**

```json
{
    "action": "set_concurrency",
    "limit": 5,
    "enabled": true
}
```

---

### 2. 收费 / 计费相关接口

管理面板“模型定价配置”可选择两种模式，点击“保存定价”后生效：

- **固定价格 `fixed`**（默认）：全天使用固定单价，可按模型自定义。已有数据库中的自定义价格会保留，升级不会覆盖。未自定义的模型采用下表高峰价。
- **官方峰谷 `peak_valley`**：按下表官方价格自动切换，不使用固定模式的自定义价格；切回固定模式后，自定义价格仍保留。

价格核对于 2026-11-10，单位为元 / 百万 tokens，来源：[DeepSeek 官方定价](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)。本项目使用内置价格表，官网后续调价需更新配置代码。

| 模型 | 时段 | 输入缓存命中 | 输入缓存未命中 | 输出 |
| --- | --- | ---: | ---: | ---: |
| deepseek-flash | 高峰 | 0.04 | 2 | 8 |
| deepseek-flash | 空闲 | 0.02 | 1 | 4 |
| deepseek-v4-pro | 高峰 | 0.30 | 9 | 27 |
| deepseek-v4-pro | 空闲 | 0.15 | 4.5 | 13.5 |

高峰为**北京时间周一至周五，排除中国法定节假日，09:00（含）–12:00（不含）、14:00（含）–18:00（不含）**。其余时间含周末全天为空闲时段，即使周末调休补班也按空闲价。节假日由 `chinesecalendar` 提供，部署前执行 `pip install -r requirements.txt`，每年国务院公布新日历后及时升级 `pip install -U chinesecalendar`。日历未覆盖的年份会返回 503 并提示升级，避免错误收费。

每次请求在转发上游之前锁定价格，流式和非流式使用相同规则，跨时段或请求中途改价不改变本次费率。费用 =（缓存命中输入 × 命中单价 + 缓存未命中输入 × 未命中单价 + 输出 × 输出单价）/ 1,000,000。

`deepseek-v4-flash`、`deepseek-v4-flash-vision-exp` 兼容为 Flash 官方价格。固定模式可为别名单独设价，未单独设置时跟随 `deepseek-flash`。峰谷模式拒绝未列入官方价格表的模型，需切到固定模式并配置其单价。

#### 获取配置

```http
GET /admin/pricing
```

返回 `mode`、当前 `period`（`fixed` / `peak` / `off_peak`）、当前生效的 `effective`、保留的 `custom`、固定模式价格 `fixed`、官方 `peak` 和 `off_peak` 价格表及 `is_default`。

#### 设置固定价格

```http
PUT /admin/pricing
Content-Type: application/json
```

```json
{
  "mode": "fixed",
  "models": {
    "deepseek-flash": {"input_hit": 0.04, "input_miss": 2, "output": 8},
    "deepseek-v4-pro": {"input_hit": 0.30, "input_miss": 9, "output": 27}
  }
}
```

三个价格字段均为必填非负有限数字。`models` 替换自定义价格表，默认模型继续保留。兼容旧调用：仅传 `models` 会保留当前计费模式；仅传 `mode` 会保留自定义价格。

#### 启用峰谷价格

```json
{"mode": "peak_valley"}
```

仍通过 `PUT /admin/pricing` 提交。返回保存后的完整配置。

#### 恢复默认

```http
DELETE /admin/pricing
```

清除自定义价格，恢复固定模式和官方高峰单价。

离线回归验证（不调用付费上游）：

```bash
python -m unittest test_billing -v
```

---

### 3. 上游与配置接口

#### 获取上游 Key（打码显示）

```
GET /admin/upstream/key
```

**响应示例：**

```json
{
    "masked": "sk-1756s***********************14a8",
    "exists": true
}
```

#### 更新上游 Key

```
POST /admin/upstream/key
Content-Type: application/json
```

```json
{ "key": "sk-新的上游key" }
```

#### 查询上游真实余额

```
GET /admin/upstream/balance
```

**响应示例：**

```json
{
    "is_available": true,
    "balance_infos": [
        {
            "currency": "CNY",
            "total_balance": "105.32",
            "granted_balance": "0.00",
            "topped_up_balance": "105.32"
        }
    ]
}
```

---

### 4. 集成示例（Python）：自动开通 + 充值

以下示例演示如何在你的业务后端中，**用管理员凭据创建一个虚拟 Key 并充值**：

```python
import requests

ADMIN_BASE = "http://127.0.0.1:8000"
ADMIN_PASSWORD = "your_admin_password"

def admin_session():
    session = requests.Session()
    session.post(f"{ADMIN_BASE}/login", data={
        "username": "admin",
        "password": ADMIN_PASSWORD
    })
    return session

# 用户支付成功后调用
def create_key_for_user(tenant: str, amount: float):
    session = admin_session()
    key = session.post(f"{ADMIN_BASE}/admin/keys", json={
        "tenant": tenant,
        "balance": 0
    }).json()["virtual_key"]

    session.put(f"{ADMIN_BASE}/admin/keys/{key}", json={
        "action": "recharge",
        "amount": amount
    })

    return key

new_key = create_key_for_user("player_001", 10.0)
print(f"用户 Key: {new_key}")
```

---

### 5. 管理 API 一览表

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/login` | 管理员登录，获取会话 |
| GET | `/logout` | 注销 |
| GET | `/admin/keys` | 获取所有虚拟 Key |
| POST | `/admin/keys` | 创建虚拟 Key |
| PUT | `/admin/keys/{key}` | 充值 / 设余额 / 并发限制 |
| GET | `/admin/pricing` | 查看定价 |
| PUT | `/admin/pricing` | 修改定价 |
| DELETE | `/admin/pricing` | 恢复默认 |
| GET | `/admin/upstream/key` | 查看打码上游 Key |
| POST | `/admin/upstream/key` | 更新上游 Key |
| GET | `/admin/upstream/balance` | 查询上游余额 |
| GET | `/admin/background` | 获取背景配置 |

---

### 6. 二次开发最佳实践（对接付费系统）

如果你打算基于这些 API 开发一套付费系统：

1. **不要向终端用户暴露 `/login`**。你的业务服务端保存管理员密码，在需要时自行调用 `/login` 换取会话。
2. 使用 `POST /admin/keys` + `PUT /admin/keys/{key}`（recharge）来实现用户开通和充值。
3. 查询余额和消费记录使用 `GET /admin/keys`。
4. 定价调整使用 `PUT /admin/pricing`，可随时修改不同模型的售价。
5. 定期备份 `keys.db`，防止数据丢失。

---

## ⚙️ 部署建议

### 使用 Nginx 反向代理（推荐）

```nginx
# 代理服务
server {
    listen 443 ssl;
    server_name api.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_buffering off;   # 流式响应必需
    }
}

# 管理面板（建议加 Basic Auth 或限制访问）
server {
    listen 443 ssl;
    server_name admin.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
    }
}
```

### 端口修改

所有端口在 `config.json` 中修改，改完重启即可。

### 备份

定期备份 `keys.db` 和 `config.json`：

```bash
# 示例：每日凌晨备份
0 3 * * * tar -zcf /backup/gateway_$(date +%F).tar.gz keys.db config.json
```

---

## ❓ FAQ

**Q：虚拟 Key 格式是什么？**  
`sk-` + 40 位随机十六进制，形如 `sk-3e5efe0e154e9aba27c50a16ad1f691e83f2bea2`。

**Q：如何给用户恢复额度？**  
管理面板 → 找到对应 Key → 输入金额 → 点击充值。或调用 `PUT /admin/keys/{key}` 接口。

**Q：余额不足时用户会看到什么？**  
收到 HTTP 402 和 JSON 错误信息 `Insufficient balance`。

**Q：流式请求如何计费？**  
流式结束后解析 usage 自动扣费；若客户端提前断开，按固定回落值（默认 0.001 元）扣费。

**Q：可以二次销售吗？**  
可以。你在管理面板自定义模型单价，自行定价即可获利或补贴成本。

**Q：背景图片不显示怎么办？**  
检查 `config.json` 中 `background.enabled` 是否为 `true`，并确认 `url` 指向的图源可以正常访问。

---

## 📄 License

本项目采用 **MIT License** 开源许可。
