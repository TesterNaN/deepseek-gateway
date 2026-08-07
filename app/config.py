# ---------- 配置常量 ----------
DATABASE = 'keys.db'
DEFAULT_BALANCE = 0.00
DEFAULT_STREAM_FALLBACK = 0.001
DEFAULT_CONCURRENCY_LIMIT = 0
DEFAULT_CONCURRENCY_ENABLED = False
UPSTREAM_BASE_URL = 'https://api.deepseek.com'

# ---------- 默认模型定价（元 / 百万 tokens） ----------
DEFAULT_PRICING = {
    "deepseek-v4-flash": {
        "input_hit": 0.02,
        "input_miss": 1.0,
        "output": 2.0
    },
    "deepseek-v4-pro": {
        "input_hit": 0.025,
        "input_miss": 3.0,
        "output": 6.0
    }
}
