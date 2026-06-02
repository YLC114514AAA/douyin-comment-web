"""
抖音评论区爬虫 — 配置常量
"""

# 评论区 API 请求 URL 特征（用于拦截识别）
COMMENT_API_PATTERN = "/aweme/v1/web/comment/list/"

# 浏览器配置
BROWSER_DATA_DIR = "browser_data"         # 持久化浏览器数据目录（保存登录态）
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
VIEWPORT_WIDTH = 1920
VIEWPORT_HEIGHT = 1080

# 滚动加载配置
SCROLL_PAUSE_MS = 200                     # 每次滚动后等待时间（毫秒）
MAX_SCROLL_ATTEMPTS = 50                  # 最大滚动次数（安全上限）
NO_NEW_COMMENTS_THRESHOLD = 3            # 连续N次无新评论则停止
REPLY_REQUEST_INTERVAL = 0.1             # 二级回复请求间隔（秒）

# 输出目录
OUTPUT_DIR = "output"

# 登录等待超时（秒）
LOGIN_TIMEOUT = 120
