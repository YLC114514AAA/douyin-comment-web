"""提取本机浏览器中抖音的 Cookie，保存为 JSON"""
from playwright.sync_api import sync_playwright
import config, json

p = sync_playwright().start()
b = p.chromium.launch_persistent_context(
    user_data_dir=config.BROWSER_DATA_DIR,
    headless=True,
)
page = b.new_page()
page.goto("https://www.douyin.com", wait_until="domcontentloaded", timeout=20000)
page.wait_for_timeout(2000)

cookies = b.cookies()
print(f"提取到 {len(cookies)} 个 Cookie")

with open("douyin_cookies.json", "w", encoding="utf-8") as f:
    json.dump(cookies, f, ensure_ascii=False, indent=2)

print("已保存到 douyin_cookies.json")
b.close()
p.stop()
