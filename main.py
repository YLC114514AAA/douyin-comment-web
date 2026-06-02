"""
抖音评论区爬虫 — 主入口

支持直接粘贴抖音分享文案（含短链接），自动解析。
按抖音号 / UID / 昵称匹配用户。

用法:
  交互模式:  python main.py
  命令模式:  python main.py --url "视频链接或分享文案" --ids "抖音号A,抖音号B"
  从文件读:  python main.py --url "..." --ids-file names.txt
"""

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta

import config
from crawler import DouyinCommentCrawler
from output import filter_by_douyin_id, save_json, save_text_report


def pause():
    """按回车退出 — 防止双击运行时窗口一闪而过"""
    print()
    input("按回车键退出...")


def open_folder(path: str):
    """在资源管理器中打开文件夹"""
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.run(["open", path])
        else:
            subprocess.run(["xdg-open", path])
    except Exception:
        pass


def load_ids_from_file(filepath: str) -> list[str]:
    """从文件读取目标抖音号/UID/昵称（一行一个）"""
    if not os.path.exists(filepath):
        print(f"[错误] 文件不存在: {filepath}")
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        ids = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
    return ids


def interactive_mode():
    """交互模式：逐步引导用户输入"""
    print("=" * 55)
    print("  抖音评论区 — 指定用户发言抓取工具")
    print("=" * 55)
    print()
    print("可以直接粘贴抖音APP里转发复制的分享文案！")
    print("（比如 \"0.53 复制打开抖音...https://v.douyin.com/xxx...\" 这样的）")
    print()

    while True:
        user_input = input("请粘贴抖音视频链接或分享文案: ").strip()
        if user_input:
            break
        print("[提示] 请输入有效内容")

    print()
    print("请输入要查询的抖音号/UID/昵称（多个用逗号分隔）:")
    print("  抖音号 = 用户主页 @后面那个，比如 \"zhangsan123\"")
    print("  UID = 纯数字ID")
    print("  昵称 = 显示名称")
    print("  也可以输入文件名（如 names.txt）从文件读取")
    print("  直接回车使用默认的 names.txt:")
    names_input = input("> ").strip()

    target_ids = []
    if not names_input:
        if os.path.exists("names.txt"):
            target_ids = load_ids_from_file("names.txt")
            print(f"[信息] 从 names.txt 加载了 {len(target_ids)} 个目标")
        else:
            print("[错误] 未找到 names.txt，请输入抖音号")
            return None
    elif names_input.endswith(".txt"):
        target_ids = load_ids_from_file(names_input)
        print(f"[信息] 从 {names_input} 加载了 {len(target_ids)} 个目标")
    else:
        target_ids = [n.strip() for n in names_input.split(",") if n.strip()]
        print(f"[信息] 查询目标: {', '.join(target_ids)}")

    if not target_ids:
        print("[错误] 未指定任何目标")
        return None

    headless_input = input("\n是否使用无头模式（不显示浏览器窗口）？(y/n，默认n): ").strip().lower()
    headless = headless_input == "y"

    return user_input, target_ids, headless


def main():
    is_cli_mode = len(sys.argv) > 1

    parser = argparse.ArgumentParser(description="抖音评论区指定用户发言抓取工具")
    parser.add_argument(
        "--url", type=str,
        help="抖音视频链接或分享文案（可直接粘贴APP分享内容）"
    )
    parser.add_argument(
        "--ids", type=str,
        help="目标抖音号/UID/昵称，多个用逗号分隔"
    )
    parser.add_argument(
        "--ids-file", type=str, default="names.txt",
        help="目标文件路径（一行一个）"
    )
    parser.add_argument(
        "--headless", action="store_true",
        help="无头模式（不显示浏览器窗口）"
    )
    args = parser.parse_args()

    if args.url:
        user_input = args.url
        headless = args.headless

        if args.ids:
            target_ids = [n.strip() for n in args.ids.split(",") if n.strip()]
        else:
            target_ids = load_ids_from_file(args.ids_file)

        if not target_ids:
            print("[错误] 请通过 --ids 或 --ids-file 指定目标抖音号")
            if not is_cli_mode:
                pause()
            sys.exit(1)
    else:
        result = interactive_mode()
        if result is None:
            pause()
            return
        user_input, target_ids, headless = result

    print()
    print(f"查询目标 ({len(target_ids)}): {', '.join(target_ids)}")
    print(f"输入内容: {user_input[:80]}{'...' if len(user_input) > 80 else ''}")
    print()

    crawler = DouyinCommentCrawler(headless=headless)

    try:
        video_url, api_comments, dom_comments = crawler.crawl(user_input)
    except Exception as e:
        print(f"[错误] 爬取失败: {e}")
        crawler.close()
        if not is_cli_mode:
            pause()
        sys.exit(1)

    # API拦截到的优先（含抖音号/UID），DOM兜底（只有昵称）
    if api_comments:
        all_comments = api_comments
        data_source = "api"
        total_replies = sum(len(c.get("replies") or []) for c in all_comments)
        print(f"[信息] 使用API拦截数据: {len(all_comments)} 条一级 + {total_replies} 条二级（含抖音号/UID）")
    elif dom_comments:
        all_comments = dom_comments
        data_source = "dom"
        total_replies = 0
        print(f"[信息] API拦截为空，使用DOM提取数据: {len(all_comments)} 条（仅含昵称）")
    else:
        all_comments = []
        data_source = "none"
        total_replies = 0
        print("[信息] API拦截和DOM提取均为空，可能评论区未加载")

    if not all_comments:
        print()
        print("=" * 50)
        print("[结果] 未能获取到任何评论数据")
        print("=" * 50)
        print("可能的原因：")
        print("  1. 评论区未能成功打开或加载")
        print("  2. 需要登录才能查看评论")
        print("  3. 该视频没有评论或评论被关闭")
        print()
        print("建议：")
        print("  1. 确认浏览器窗口中能看到评论区内容")
        print("  2. 如果看不到，请先在浏览器中手动登录抖音")
        print("  3. 尝试删除 browser_data/ 文件夹后重试（清理旧的登录态）")
        crawler.close()
        if not is_cli_mode:
            pause()
        return

    filtered = filter_by_douyin_id(all_comments, target_ids)

    if not filtered:
        print()
        print("=" * 50)
        print("[结果] 未找到指定用户的评论")
        print("=" * 50)
        print(f"已抓取 {len(all_comments)} 条一级评论" + (f" + {total_replies} 条二级回复" if total_replies > 0 else "") + "，但没有任何一条匹配到指定目标。")
        print()
        print("可能的原因：")
        print("  1. 抖音号/UID 拼写不正确（大小写不敏感）")
        print("  2. 该用户没有在此视频下留过言")
        print("  3. 用户没有设置抖音号（试试用他的UID或昵称）")
        if dom_comments and not api_comments:
            print("  4. 当前使用DOM提取模式，只匹配昵称（无抖音号数据）")
        print()
        print("提示：可以用记事本打开 output/ 目录下的 JSON 文件")
        print("查看所有评论者的 nickname / unique_id / uid 来确认正确的标识。")
        crawler.close()
        if not is_cli_mode:
            pause()
        return

    beijing_tz = timezone(timedelta(hours=8))
    timestamp = datetime.now(beijing_tz).strftime("%Y%m%d_%H%M%S")
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)

    json_path = os.path.join(config.OUTPUT_DIR, f"results_{timestamp}.json")
    txt_path = os.path.join(config.OUTPUT_DIR, f"results_{timestamp}.txt")

    json_data = {
        "video_url": video_url,
        "scraped_at": datetime.now(beijing_tz).isoformat(),
        "queried_targets": target_ids,
        "total_comments_scraped": len(all_comments),
        "total_replies_scraped": total_replies,
        "data_source": data_source,
        "matched_comments": filtered,
    }
    save_json(json_data, json_path)

    save_text_report(filtered, target_ids, video_url, len(all_comments), txt_path)

    print()
    print("=" * 55)
    print(f"  全部完成！")
    print(f"  TXT 报告: {txt_path}")
    print(f"  JSON 数据: {json_path}")
    print("=" * 55)

    crawler.close()

    print()
    print(f"结果已保存到: {os.path.abspath(config.OUTPUT_DIR)}")

    if not is_cli_mode:
        pause()


if __name__ == "__main__":
    main()
