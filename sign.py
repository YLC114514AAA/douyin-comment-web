"""
抖音 API 参数构建 + a_bogus 签名
仿 DouyinComments/common.py，负责：
  - COMMON_PARAMS / COMMON_HEADERS
  - webid 提取
  - cookie 参数提取 (verifyFp, fp, 屏幕信息等)
  - a_bogus 签名
"""

import os
import random
import re
import string
import urllib.parse

_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

# ---- 在 import execjs 之前确保 Node.js 在 PATH 中 ----
_NODE_DIRS = [
    _PROJECT_DIR,
]
# 检查 nodejs-bin pip 包
try:
    import nodejs as _nodejs_pkg
    _nodejs_dir = os.path.dirname(_nodejs_pkg.__file__)
    _node_exe = os.path.join(_nodejs_dir, "node.exe")
    if os.path.exists(_node_exe):
        _NODE_DIRS.append(_nodejs_dir)
except ImportError:
    pass
for _nd in _NODE_DIRS:
    if os.path.exists(os.path.join(_nd, "node.exe")):
        os.environ["PATH"] = _nd + os.pathsep + os.environ.get("PATH", "")
        break

import execjs  # noqa: E402
import httpx   # noqa: E402

# ---- 加载 douyin.js ----
_JS_PATH = os.path.join(_PROJECT_DIR, "douyin.js")
with open(_JS_PATH, encoding="utf-8") as f:
    _DOUYIN_JS = execjs.compile(f.read())

# ---- 通用请求参数 ----
COMMON_PARAMS = {
    "device_platform": "webapp",
    "aid": "6383",
    "channel": "channel_pc_web",
    "update_version_code": "170400",
    "pc_client_type": "1",
    "version_code": "190500",
    "version_name": "19.5.0",
    "cookie_enabled": "true",
    "screen_width": "2560",
    "screen_height": "1440",
    "browser_language": "zh-CN",
    "browser_platform": "Win32",
    "browser_name": "Chrome",
    "browser_version": "126.0.0.0",
    "browser_online": "true",
    "engine_name": "Blink",
    "engine_version": "126.0.0.0",
    "os_name": "Windows",
    "os_version": "10",
    "cpu_core_num": "24",
    "device_memory": "8",
    "platform": "PC",
    "downlink": "10",
    "effective_type": "4g",
    "round_trip_time": "50",
}

# ---- 通用请求头 ----
COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "sec-ch-ua-platform": '"Windows"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua": '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
    "referer": "https://www.douyin.com/?recommend=1",
    "priority": "u=1, i",
    "pragma": "no-cache",
    "cache-control": "no-cache",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
    "accept": "application/json, text/plain, */*",
    "dnt": "1",
}


def _random_ms_token(length: int = 120) -> str:
    """生成随机 msToken"""
    base = "ABCDEFGHIGKLMNOPQRSTUVWXYZabcdefghigklmnopqrstuvwxyz0123456789="
    return "".join(random.choice(base) for _ in range(length))


def get_webid(cookie_str: str) -> str | None:
    """从 douyin.com 首页 HTML 提取 webid (user_unique_id)"""
    headers = dict(COMMON_HEADERS)
    headers["Cookie"] = cookie_str
    try:
        resp = httpx.get("https://www.douyin.com/?recommend=1", headers=headers, timeout=15)
        if resp.status_code != 200:
            return None
        m = re.search(r'\\"user_unique_id\\":\\"(\d+)\\"', resp.text)
        if m:
            return m.group(1)
    except Exception:
        pass
    return None


def build_request_params(
    uri: str,
    params: dict,
    cookie_dict: dict,
    user_agent: str | None = None,
) -> dict:
    """
    构建完整的请求参数：合并 COMMON_PARAMS + 提取 cookie 关键值 + 签名
    仿 DouyinComments/common.py 的 common() + deal_params()
    """
    # 1. 合并通用参数
    full_params = dict(COMMON_PARAMS)
    full_params.update(params)
    full_params["msToken"] = _random_ms_token()

    # 2. 从 cookie 提取参数
    if cookie_dict:
        full_params["screen_width"] = cookie_dict.get("dy_swidth", "2560")
        full_params["screen_height"] = cookie_dict.get("dy_sheight", "1440")
        full_params["cpu_core_num"] = cookie_dict.get("device_web_cpu_core", "24")
        full_params["device_memory"] = cookie_dict.get("device_web_memory_size", "8")
        s_v_web_id = cookie_dict.get("s_v_web_id")
        if s_v_web_id:
            full_params["verifyFp"] = s_v_web_id
            full_params["fp"] = s_v_web_id

    # 3. webid（这里需要调用方传入已获取的 webid）
    # 由调用方在外部获取后传入 params 或直接设置

    # 4. 生成签名
    ua = user_agent or COMMON_HEADERS["User-Agent"]
    query_parts = []
    for k, v in full_params.items():
        query_parts.append(f"{k}={urllib.parse.quote(str(v))}")
    query = "&".join(query_parts)

    sign_fn = "sign_reply" if "/reply" in uri else "sign_datail"
    a_bogus = _DOUYIN_JS.call(sign_fn, query, ua)
    full_params["a_bogus"] = a_bogus

    return full_params
