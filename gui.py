"""
抖音评论区爬虫 - GUI 界面
CustomTkinter 桌面版，暗色主题，彩色结果渲染
"""

import io
import os
import sys
import threading
import traceback
import webbrowser

import customtkinter as ctk
import httpx
from CTkMessagebox import CTkMessagebox

from crawler import DouyinCommentCrawler
from output import filter_by_douyin_id, save_json, save_text_report
from output import group_by_user, compute_stats, _format_time
import config

# 主题
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class PrintRedirector(io.StringIO):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def write(self, s):
        super().write(s)
        if s.strip():
            self.callback(s)

    def flush(self):
        pass


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("海森堡抖音评论查询")
        self.geometry("860x720")
        self.minsize(750, 550)

        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - 860) // 2
        y = (sh - 720) // 2
        self.geometry(f"860x720+{x}+{y}")

        self.crawler = None
        self.is_running = False
        self._img_store = {}
        self._img_counter = 0

        self._build_ui()
        sys.stdout = PrintRedirector(self._log)

    # ======================== UI 构建 ========================

    def _build_ui(self):
        # 标题
        title = ctk.CTkLabel(
            self, text="抖音评论区 - 指定用户发言抓取",
            font=ctk.CTkFont(size=22, weight="bold"),
        )
        title.pack(pady=(20, 5))

        subtitle = ctk.CTkLabel(
            self, text="支持分享文案 · 抖音号 · UID · 昵称匹配 · 含二级回复",
            font=ctk.CTkFont(size=12), text_color="gray",
        )
        subtitle.pack(pady=(0, 15))

        # 输入卡片
        card = ctk.CTkFrame(self)
        card.pack(fill="x", padx=30, pady=(0, 10))

        ctk.CTkLabel(card, text="视频链接 / 分享文案", font=ctk.CTkFont(size=13)).pack(
            anchor="w", padx=15, pady=(15, 2))
        self.url_entry = ctk.CTkEntry(card, height=36, placeholder_text="粘贴抖音分享文案或视频链接...")
        self.url_entry.pack(fill="x", padx=15, pady=(0, 10))
        self._enable_paste(self.url_entry)

        ctk.CTkLabel(card, text="目标用户 (抖音号 / UID / 昵称, 逗号分隔 或 填文件名)",
                     font=ctk.CTkFont(size=13)).pack(anchor="w", padx=15, pady=(0, 2))
        id_row = ctk.CTkFrame(card, fg_color="transparent")
        id_row.pack(fill="x", padx=15, pady=(0, 15))

        self.ids_entry = ctk.CTkEntry(id_row, height=36, placeholder_text="例: zhangsan, lisi 或 names.txt")
        self.ids_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self._enable_paste(self.ids_entry)

        self.file_btn = ctk.CTkButton(
            id_row, text="浏览文件", width=90, font=ctk.CTkFont(size=12),
            command=self._browse_ids_file)
        self.file_btn.pack(side="right")

        self.headless_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(card, text="无头模式 (不显示浏览器窗口)", variable=self.headless_var,
                        font=ctk.CTkFont(size=12)).pack(anchor="w", padx=15, pady=(0, 15))

        # 按钮
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=30, pady=(0, 10))

        self.start_btn = ctk.CTkButton(
            btn_row, text="  开始抓取", height=40, width=160,
            font=ctk.CTkFont(size=14, weight="bold"), command=self._start_crawl)
        self.start_btn.pack(side="left", padx=(0, 10))

        self.open_btn = ctk.CTkButton(
            btn_row, text="  打开结果文件夹", height=40, width=150,
            font=ctk.CTkFont(size=13), fg_color="transparent", border_width=1,
            command=self._open_output)
        self.open_btn.pack(side="left")

        self.stop_btn = ctk.CTkButton(
            btn_row, text="  停止", height=40, width=100, font=ctk.CTkFont(size=13),
            fg_color="#8B0000", hover_color="#A00000",
            command=self._stop_crawl, state="disabled")
        self.stop_btn.pack(side="right")

        # 提示说明
        hint = ctk.CTkFrame(self, fg_color="transparent")
        hint.pack(fill="x", padx=30, pady=(0, 8))
        ctk.CTkLabel(
            hint, text=(
                "ℹ 快捷键：Ctrl+V 粘贴 | Ctrl+C 复制 | Ctrl+A 全选 | 右键菜单"
            ),
            font=ctk.CTkFont(size=10), text_color="#777777",
        ).pack(side="left")
        ctk.CTkLabel(
            hint, text=(
                "   ℹ 一级评论 = 直接回复视频的评论  |  二级评论 = 回复别人评论的回复"
            ),
            font=ctk.CTkFont(size=10), text_color="#666666",
        ).pack(side="right")

        # 双标签页
        self.tab_view = ctk.CTkTabview(self)
        self.tab_view.pack(fill="both", expand=True, padx=30, pady=(5, 5))
        self.tab_view.add("运行日志")
        self.tab_view.add("抓取结果")
        self.tab_view.set("运行日志")

        self.log_box = ctk.CTkTextbox(
            self.tab_view.tab("运行日志"),
            font=ctk.CTkFont(size=12, family="Consolas"), wrap="word")
        self.log_box.pack(fill="both", expand=True)

        self.result_box = ctk.CTkTextbox(
            self.tab_view.tab("抓取结果"),
            font=ctk.CTkFont(size=13), wrap="word")
        self.result_box.pack(fill="both", expand=True)

        # 结果文字标签样式
        tb = self.result_box._textbox
        tb.tag_config("h1", foreground="#FFD700",
                      font=("Microsoft YaHei UI", 16, "bold"), spacing3=8)
        tb.tag_config("h2", foreground="#00BFFF",
                      font=("Microsoft YaHei UI", 14, "bold"), spacing3=8)
        tb.tag_config("h3", foreground="#FFA500",
                      font=("Microsoft YaHei UI", 12, "bold"), spacing1=6)
        tb.tag_config("likes", foreground="#FF6B6B",
                      font=("Microsoft YaHei UI", 12, "bold"))
        tb.tag_config("time", foreground="#888888",
                      font=("Microsoft YaHei UI", 11))
        tb.tag_config("body", foreground="#E0E0E0",
                      font=("Microsoft YaHei UI", 12))
        tb.tag_config("reply_body", foreground="#B0B0B0",
                      font=("Microsoft YaHei UI", 11))
        tb.tag_config("reply_user", foreground="#87CEEB",
                      font=("Microsoft YaHei UI", 11, "bold"))
        tb.tag_config("separator", foreground="#555555",
                      font=("Microsoft YaHei UI", 10))
        tb.tag_config("summary", foreground="#FFFFFF",
                      font=("Microsoft YaHei UI", 13, "bold"))
        tb.tag_config("stat", foreground="#4FC3F7",
                      font=("Microsoft YaHei UI", 13))
        tb.tag_config("image_url", foreground="#66BB6A",
                      font=("Consolas", 10))
        tb.tag_config("hl", background="#5A4500")
        tb.tag_config("tree", foreground="#00CED1",
                      font=("Microsoft YaHei UI", 12, "bold"))
        tb.tag_config("level", foreground="#666666",
                      font=("Microsoft YaHei UI", 10))
        tb.tag_config("arrow", foreground="#FF8C00",
                      font=("Microsoft YaHei UI", 11, "bold"))

        self.result_box.insert("1.0", "抓取完成后，结果将在此显示。\n\n"
                               "也可以点击下方  打开结果文件夹 查看 JSON / TXT 文件。")

        # 状态栏
        self.status_bar = ctk.CTkLabel(
            self, text="就绪 | 请输入视频链接和目标用户后点击「开始抓取」",
            font=ctk.CTkFont(size=11), text_color="gray", anchor="w")
        self.status_bar.pack(fill="x", padx=30, pady=(0, 15))

    # ======================== 粘贴支持 ========================

    def _enable_paste(self, widget):
        widget.bind("<Control-v>", lambda e: self._do_paste(widget))
        widget.bind("<Control-c>", lambda e: self._do_copy(widget))
        widget.bind("<Control-a>", lambda e: self._do_select_all(widget))
        widget.bind("<Button-3>", lambda e: self._right_click_menu(e, widget))

    def _do_paste(self, widget):
        try:
            widget.insert("insert", self.clipboard_get())
        except Exception:
            pass

    def _do_copy(self, widget):
        try:
            sel = widget.selection_get()
            if sel:
                self.clipboard_clear()
                self.clipboard_append(sel)
        except Exception:
            pass

    def _do_select_all(self, widget):
        widget.selection_range(0, "end")

    def _right_click_menu(self, event, widget):
        from tkinter import Menu
        menu = Menu(self, tearoff=0)
        menu.add_command(label="粘贴", command=lambda: self._do_paste(widget))
        menu.add_command(label="复制", command=lambda: self.clipboard_append(widget.selection_get()))
        menu.add_command(label="剪切", command=lambda: self._do_cut(widget))
        menu.add_command(label="全选", command=lambda: widget.selection_range(0, "end"))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _do_cut(self, widget):
        try:
            self.clipboard_append(widget.selection_get())
            widget.delete("sel.first", "sel.last")
        except Exception:
            pass

    # ======================== 日志 ========================

    def _log(self, text: str):
        self.after(0, lambda: self._append_log(text))

    def _append_log(self, text: str):
        self.log_box.insert("end", text.rstrip() + "\n")
        self.log_box.see("end")

    def _set_status(self, text: str, color: str = "gray"):
        self.after(0, lambda: self.status_bar.configure(text=text, text_color=color))

    # ======================== 结果渲染 ========================

    def _render_results(self, filtered, total_parent, total_replies, video_url, target_ids):
        """在结果面板用彩色标签渲染"""
        from datetime import datetime, timezone, timedelta

        box = self.result_box
        box.configure(state="normal")
        box.delete("1.0", "end")
        tb = box._textbox

        beijing_tz = timezone(timedelta(hours=8))
        now = datetime.now(beijing_tz).strftime("%Y-%m-%d %H:%M:%S")

        # 目标用户标识集合
        target_set = {t.strip().lower() for t in target_ids if t.strip()}
        def _is_target(c):
            return bool({
                str(c.get("unique_id") or "").lower(),
                str(c.get("uid") or "").lower(),
                str(c.get("short_id") or "").lower(),
                str(c.get("nickname") or "").lower(),
            } & target_set)

        # 收集目标用户所有发言（含深层回复），按时间排序编号
        all_target_items = []
        def _collect_target(item):
            if _is_target(item):
                all_target_items.append(item)
            for sub in item.get("replies") or []:
                _collect_target(sub)
        for c in filtered:
            _collect_target(c)
        all_target_items.sort(key=lambda x: x.get("create_time", 0))

        # 圆圈数字 ①-⑳ = ①-⑳
        CIRCLE = [
            "①", "②", "③", "④", "⑤",
            "⑥", "⑦", "⑧", "⑨", "⑩",
            "⑪", "⑫", "⑬", "⑭", "⑮",
            "⑯", "⑰", "⑱", "⑲", "⑳",
        ]

        # 标签辅助
        def _tt(tag, highlight):
            return (tag, "hl") if highlight else tag

        # 给每条目标发言打上序号标记
        item_num = {}
        for i, item in enumerate(all_target_items):
            item_num[id(item)] = CIRCLE[i] if i < len(CIRCLE) else f"({i + 1})"

        # 目标统计
        target_total_likes = sum(it.get("digg_count", 0) for it in all_target_items)
        target_total_count = len(all_target_items)
        target_primary = sum(1 for c in filtered if _is_target(c))
        target_secondary = target_total_count - target_primary

        groups = group_by_user(filtered)

        # ── 头部
        tb.insert("end", "\n")
        tb.insert("end", "  ◆  抖音评论区抓取结果\n", "h1")
        tb.insert("end", "  " + "─" * 48 + "\n", "separator")

        tb.insert("end", "  视频  ", "summary")
        tb.insert("end", f"{video_url[:55]}\n", "time")
        tb.insert("end", "  时间  ", "summary")
        tb.insert("end", f"{now}\n", "time")
        tb.insert("end", "  查询  ", "summary")
        tb.insert("end", f"{', '.join(target_ids[:4])}{'...' if len(target_ids) > 4 else ''}\n", "body")
        tb.insert("end", f"  一级评论 {target_primary} 条  ·  二级回复 {target_secondary} 条\n", "stat")
        tb.insert("end", "  目标用户评论总点赞数  ", "summary")
        tb.insert("end", f"{target_total_likes}\n", "likes")
        tb.insert("end", "  " + "─" * 48 + "\n\n", "separator")

        # ── 每个用户
        for _group_name, user_comments in groups.items():
            c0 = user_comments[0]

            display = c0.get("nickname", "???")
            unique_id = c0.get("unique_id", "")
            if unique_id:
                display += f"  ·  {unique_id}"
            display += f"  ·  UID {c0.get('uid', '')}"

            tb.insert("end", f"\n  ▸ {display}\n", "h2")

            for c in user_comments:
                likes = c["digg_count"]
                t = _format_time(c["create_time"])
                ip = c.get("ip_label", "-")

                is_me = _is_target(c)
                circle_mark = item_num.get(id(c), "")

                tb.insert("end", "    ", _tt("body", is_me))
                tb.insert("end", f"❤ {likes}  ", _tt("likes", is_me))
                tb.insert("end", f"{t}  ", _tt("time", is_me))
                tb.insert("end", f"IP: {ip}", _tt("time", is_me))
                cb = _tt("h3", is_me)
                if circle_mark:
                    tb.insert("end", f"  {circle_mark}", cb)
                tb.insert("end", "  · 一级评论", _tt("level", is_me))
                if is_me:
                    tb.insert("end", "  ◀", "arrow")
                tb.insert("end", "\n")
                tb.insert("end", f"        {c['text']}\n", _tt("body", is_me))

                images = c.get("images", [])
                stickers = c.get("stickers", [])
                all_media = images + stickers
                if all_media:
                    idx = self._img_counter
                    self._img_counter += 1
                    self._img_store[idx] = all_media
                    tag = f"img_{idx}"
                    tb.tag_config(tag, foreground="#4FC3F7",
                                  font=("Microsoft YaHei UI", 10, "underline"))
                    tb.tag_bind(tag, "<Button-1>",
                                lambda e, i=idx: self._open_image_viewer(i))
                    tb.insert("end", f"        [查看图片 ({len(all_media)}张)]\n", _tt(tag, is_me))

                # 递归渲染回复 — 文件树风格
                _level_label = ["", "二级评论", "二级评论", "二级评论"]

                def _render_replies(replies, depth, base_indent):
                    for ri, r in enumerate(replies):
                        is_last = ri == len(replies) - 1
                        r_user = r.get("nickname", "???")
                        r_likes = r.get("digg_count", 0)
                        r_time = _format_time(r.get("create_time", 0))
                        r_circle = item_num.get(id(r), "")
                        r_is_me = _is_target(r)
                        tree_tag = ("tree", "hl") if r_is_me else "tree"
                        level_name = _level_label[min(depth, 3)]

                        branch = "└── " if is_last else "├── "
                        branch_cont = "    " if is_last else "│   "

                        # 头行：分支 + 用户信息
                        tb.insert("end", f"\n      {base_indent}")
                        tb.insert("end", branch, tree_tag)
                        tb.insert("end", f"{r_user}", _tt("reply_user", r_is_me))
                        tb.insert("end", f"  ❤ {r_likes}  ", _tt("likes", r_is_me))
                        tb.insert("end", f"{r_time}", _tt("time", r_is_me))
                        if r_circle:
                            tb.insert("end", f"  {r_circle}", _tt("h3", r_is_me))
                        if level_name:
                            tb.insert("end", f"  · {level_name}", _tt("level", r_is_me))
                        if r_is_me:
                            tb.insert("end", "  ◀", "arrow")
                        tb.insert("end", "\n")

                        # 内容行
                        tb.insert("end", f"      {base_indent}")
                        tb.insert("end", branch_cont, tree_tag)
                        tb.insert("end", f"{r.get('text', '')}\n", _tt("reply_body", r_is_me))

                        # 图片链接
                        r_images = r.get("images", [])
                        r_stickers = r.get("stickers", [])
                        r_media = r_images + r_stickers
                        if r_media:
                            idx = self._img_counter
                            self._img_counter += 1
                            self._img_store[idx] = r_media
                            tag = f"img_{idx}"
                            tb.tag_config(tag, foreground="#4FC3F7",
                                          font=("Microsoft YaHei UI", 10, "underline"))
                            tb.tag_bind(tag, "<Button-1>",
                                        lambda e, i=idx: self._open_image_viewer(i))
                            tb.insert("end", f"      {base_indent}{branch_cont}"
                                      f"[查看图片 ({len(r_media)}张)]\n", _tt(tag, r_is_me))

                        # 递归更深层
                        sub_replies = r.get("replies") or []
                        if sub_replies:
                            _render_replies(sub_replies, depth + 1,
                                            base_indent + branch_cont)

                replies = c.get("replies") or []
                _render_replies(replies, 1, "")

                tb.insert("end", "\n")

            tb.insert("end", "  " + "─" * 48 + "\n", "separator")

        # ── 底部
        tb.insert("end", f"\n  ◆  目标用户共发 {target_primary} 条一级评论 + {target_secondary} 条二级回复 = {target_total_count} 条，总点赞数 {target_total_likes}\n\n", "h1")
        box.see("1.0")
        self.tab_view.set("抓取结果")

    # ======================== 按钮动作 ========================

    def _browse_ids_file(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="选择目标用户文件",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")])
        if path:
            self.ids_entry.delete(0, "end")
            self.ids_entry.insert(0, path)

    def _open_image_viewer(self, idx):
        """弹出图片预览窗口"""
        from PIL import Image
        from io import BytesIO

        urls = self._img_store.get(idx, [])
        if not urls:
            return

        win = ctk.CTkToplevel(self)
        win.title(f"图片预览 — 共 {len(urls)} 张")
        win.geometry("700x600")
        win.after(10, win.focus)

        current = [0]

        img_label = ctk.CTkLabel(win, text="加载中...")
        img_label.pack(fill="both", expand=True, padx=10, pady=(10, 5))

        info_label = ctk.CTkLabel(win, text=f"第 1 / {len(urls)} 张",
                                  font=ctk.CTkFont(size=12))
        info_label.pack(pady=(0, 5))

        def show_image(index):
            if 0 <= index < len(urls):
                try:
                    resp = httpx.get(urls[index], timeout=15,
                                    headers={"Referer": "https://www.douyin.com/"})
                    img = Image.open(BytesIO(resp.content))
                    w, h = img.size
                    scale = min(650 / w, 480 / h, 1.0)
                    new_w, new_h = int(w * scale), int(h * scale)
                    ctk_img = ctk.CTkImage(img, size=(new_w, new_h))
                    img_label.configure(image=ctk_img, text="")
                    info_label.configure(text=f"第 {index + 1} / {len(urls)} 张")
                    current[0] = index
                except Exception as e:
                    img_label.configure(image=None, text=f"加载失败\n{urls[index]}\n\n{e}")

        btn_row = ctk.CTkFrame(win, fg_color="transparent")
        btn_row.pack(pady=(0, 10))

        ctk.CTkButton(btn_row, text="< 上一张", width=90, font=ctk.CTkFont(size=12),
                      command=lambda: show_image(current[0] - 1)).pack(side="left", padx=3)
        ctk.CTkButton(btn_row, text="下一张 >", width=90, font=ctk.CTkFont(size=12),
                      command=lambda: show_image(current[0] + 1)).pack(side="left", padx=3)
        ctk.CTkButton(btn_row, text="在浏览器打开", width=110, font=ctk.CTkFont(size=12),
                      command=lambda: webbrowser.open(urls[current[0]])).pack(side="left", padx=3)

        show_image(0)

    def _open_output(self):
        try:
            os.startfile(os.path.abspath(config.OUTPUT_DIR))
        except Exception:
            pass

    def _stop_crawl(self):
        self._set_status("正在停止...", "orange")
        self.is_running = False
        if self.crawler:
            try:
                self.crawler.close()
            except Exception:
                pass
        self._set_ui_state(False)

    def _set_ui_state(self, running: bool):
        state = "normal" if not running else "disabled"
        self.start_btn.configure(state="disabled" if running else "normal")
        self.stop_btn.configure(state="normal" if running else "disabled")
        self.url_entry.configure(state=state)
        self.ids_entry.configure(state=state)
        self.file_btn.configure(state=state)

    def _start_crawl(self):
        if self.is_running:
            return

        url = self.url_entry.get().strip()
        ids_raw = self.ids_entry.get().strip()

        if not url:
            CTkMessagebox(title="提示", message="请输入视频链接或分享文案", icon="warning")
            return
        if not ids_raw:
            CTkMessagebox(title="提示", message="请输入目标用户或文件名", icon="warning")
            return

        if ids_raw.endswith(".txt"):
            if not os.path.exists(ids_raw):
                CTkMessagebox(title="错误", message=f"文件不存在: {ids_raw}", icon="cancel")
                return
            with open(ids_raw, "r", encoding="utf-8") as f:
                target_ids = [line.strip() for line in f
                              if line.strip() and not line.strip().startswith("#")]
        else:
            target_ids = [n.strip() for n in ids_raw.split(",") if n.strip()]

        if not target_ids:
            CTkMessagebox(title="提示", message="未能解析到有效的目标用户", icon="warning")
            return

        self._set_ui_state(True)
        self.is_running = True
        self._set_status("正在启动浏览器...", "cyan")
        self.log_box.delete("1.0", "end")

        threading.Thread(target=self._run_crawl, args=(url, target_ids), daemon=True).start()

    def _run_crawl(self, url, target_ids):
        try:
            headless = self.headless_var.get()
            print(f"[信息] 查询目标 ({len(target_ids)}): "
                  f"{', '.join(target_ids[:8])}{'...' if len(target_ids) > 8 else ''}")
            print(f"[信息] 无头模式: {'是' if headless else '否'}")
            print()

            self.crawler = DouyinCommentCrawler(headless=headless)
            video_url, api_comments, dom_comments = self.crawler.crawl(url)

            if api_comments:
                all_comments = api_comments
                total_replies = sum(len(c.get("replies") or []) for c in all_comments)
                print(f"[信息] 使用 API 数据: {len(all_comments)} 条一级 + {total_replies} 条二级")
            elif dom_comments:
                all_comments = dom_comments
                total_replies = 0
                print("[信息] API 拦截为空，使用 DOM 数据 (仅含昵称)")
            else:
                all_comments = []
                total_replies = 0
                print("[警告] 未获取到任何评论数据")

            if not all_comments:
                print("[结果] 未获取到评论，请确认浏览器中能看到评论区")
                self._set_status("完成 | 无数据", "orange")
                return

            filtered = filter_by_douyin_id(all_comments, target_ids)

            if not filtered:
                print(f"[结果] 已抓取 {len(all_comments)} 条评论，无匹配")
                print("[提示] 可查看 output/ 下 JSON 文件确认评论区用户标识")
                self._set_status("完成 | 无匹配", "orange")
                return

            from datetime import datetime, timezone, timedelta
            beijing_tz = timezone(timedelta(hours=8))
            ts = datetime.now(beijing_tz).strftime("%Y%m%d_%H%M%S")
            os.makedirs(config.OUTPUT_DIR, exist_ok=True)

            json_path = os.path.join(config.OUTPUT_DIR, f"results_{ts}.json")
            txt_path = os.path.join(config.OUTPUT_DIR, f"results_{ts}.txt")

            save_json({
                "video_url": video_url,
                "scraped_at": datetime.now(beijing_tz).isoformat(),
                "queried_targets": target_ids,
                "total_comments_scraped": len(all_comments),
                "total_replies_scraped": total_replies,
                "data_source": "api" if api_comments else "dom",
                "matched_comments": filtered,
            }, json_path)
            save_text_report(filtered, target_ids, video_url, len(all_comments), txt_path)

            matched_replies = sum(len(c.get("replies") or []) for c in filtered)
            total_items = len(filtered) + matched_replies

            print(f"\n[完成] 匹配 {len(filtered)} 条评论 + {matched_replies} 条回复 = 共 {total_items} 条")
            print(f"[完成] JSON: {json_path}")
            print(f"[完成] TXT:  {txt_path}")
            self._set_status(f"完成 | 匹配 {total_items} 条发言", "green")

            self.after(0, lambda: self._render_results(
                filtered, len(all_comments), total_replies, video_url, target_ids))

            self.after(0, lambda: CTkMessagebox(
                title="抓取完成",
                message=f"匹配到 {len(filtered)} 条评论 + {matched_replies} 条回复\n"
                        f"共 {total_items} 条发言\n\n"
                        f"结果已显示在「抓取结果」标签页",
                icon="check"))
        except Exception as e:
            print(f"[错误] {e}")
            traceback.print_exc()
            self._set_status("出错", "red")
            self.after(0, lambda: CTkMessagebox(
                title="抓取出错",
                message=f"发生错误:\n{str(e)[:300]}\n\n详情请查看日志",
                icon="cancel"))

        finally:
            if self.crawler:
                try:
                    self.crawler.close()
                except Exception:
                    pass
            self.is_running = False
            self.after(0, lambda: self._set_ui_state(False))


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
