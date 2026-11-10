# ---------- 配置常量 ----------
DATABASE = 'keys.db'
DEFAULT_BALANCE = 0.00
DEFAULT_STREAM_FALLBACK = 0.001
DEFAULT_CONCURRENCY_LIMIT = 0
DEFAULT_CONCURRENCY_ENABLED = False
UPSTREAM_BASE_URL = 'https://api.deepseek.com'

# ---------- 默认模型定价（元 / 百万 tokens） ----------
# 官方价格核对日期：2026-11-10。固定模式默认采用高峰价。
# https://api-docs.deepseek.com/zh-cn/quick_start/pricing/
DEFAULT_PRICING = {
    "deepseek-flash": {"input_hit": 0.04, "input_miss": 2.0, "output": 8.0},
    "deepseek-v4-pro": {"input_hit": 0.30, "input_miss": 9.0, "output": 27.0},
}
MODEL_ALIASES = {
    "deepseek-v4-flash": "deepseek-flash",
    "deepseek-v4-flash-vision-exp": "deepseek-flash",
}
DEFAULT_PRICING_MODE = "fixed"
