"""
海森堡抖音评论查询 — Web 后端
FastAPI + ThreadPoolExecutor 任务队列
"""

import io
import os
import sys
import threading
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

# 把项目根目录加入 sys.path，保证 import 爬虫模块正常
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crawler import DouyinCommentCrawler
from output import filter_by_douyin_id
from auth import register_auth_routes, require_auth

app = FastAPI(title="海森堡抖音评论查询")

# 任务存储 + 并发控制
_tasks: dict[str, dict] = {}
_lock = threading.Lock()
_semaphore = threading.BoundedSemaphore(4)  # 最多同时 4 个任务


def _enqueue_task(url: str, targets: list[str]) -> str:
    task_id = f"TK-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:4]}"
    with _lock:
        _tasks[task_id] = {
            "task_id": task_id,
            "status": "queued",
            "created_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
            "logs": [],
            "progress": {"parent_total": 0, "replies_done": 0, "replies_total": 0},
            "result": None,
            "error": None,
        }
    t = threading.Thread(target=_run_crawl_task, args=(task_id, url, targets), daemon=True)
    t.start()
    return task_id


def _run_crawl_task(task_id: str, url: str, targets: list[str]):
    # 等信号量（排队 + 限并发）
    _semaphore.acquire()

    with _lock:
        if task_id in _tasks:
            _tasks[task_id]["status"] = "running"

    log_buffer = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = log_buffer

    crawler = None
    try:
        crawler = DouyinCommentCrawler(headless=True)
        video_url, api_comments, dom_comments = crawler.crawl(url)

        all_comments = api_comments if api_comments else dom_comments
        total_replies = sum(len(c.get("replies") or []) for c in all_comments)

        with _lock:
            if task_id in _tasks:
                _tasks[task_id]["progress"]["parent_total"] = len(all_comments)
                _tasks[task_id]["progress"]["replies_total"] = total_replies

        if not all_comments:
            with _lock:
                if task_id in _tasks:
                    _tasks[task_id]["status"] = "done"
                    _tasks[task_id]["result"] = {"matched": [], "video_url": video_url}
            return

        filtered = filter_by_douyin_id(all_comments, targets)
        matched_replies = sum(len(c.get("replies") or []) for c in filtered)
        total_matched = len(filtered) + matched_replies

        result = {
            "video_url": video_url,
            "targets": targets,
            "total_scraped": len(all_comments),
            "total_replies_scraped": total_replies,
            "matched_parent": len(filtered),
            "matched_replies": matched_replies,
            "total_matched": total_matched,
            "comments": filtered,
            "scraped_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        }

        with _lock:
            if task_id in _tasks:
                _tasks[task_id]["status"] = "done"
                _tasks[task_id]["result"] = result

    except Exception as e:
        with _lock:
            if task_id in _tasks:
                _tasks[task_id]["status"] = "failed"
                _tasks[task_id]["error"] = str(e)

    finally:
        sys.stdout = old_stdout
        captured = log_buffer.getvalue()
        lines = [l.strip() for l in captured.splitlines() if l.strip()]
        with _lock:
            if task_id in _tasks:
                _tasks[task_id]["logs"].extend(lines)
        log_buffer.close()
        if crawler:
            try:
                crawler.close()
            except Exception:
                pass
        _semaphore.release()


# ======================== API 路由 ========================

@app.post("/api/crawl")
@require_auth
async def api_crawl(request: Request):
    body = await request.json()
    url = (body.get("url") or "").strip()
    targets_raw = (body.get("targets") or "").strip()

    if not url:
        return JSONResponse({"error": "请输入视频链接"}, status_code=400)
    if not targets_raw:
        return JSONResponse({"error": "请输入目标用户"}, status_code=400)

    targets = [t.strip() for t in targets_raw.split(",") if t.strip()]
    if not targets:
        return JSONResponse({"error": "无法解析目标用户"}, status_code=400)

    task_id = _enqueue_task(url, targets)

    # 计算排队位置（包含当前任务自身）
    with _lock:
        queued = [t for t in _tasks.values() if t["status"] == "queued"]
        queued.sort(key=lambda t: t["created_at"])
        queue_pos = 1
        for i, t in enumerate(queued):
            if t["task_id"] == task_id:
                queue_pos = i + 1
                break

    return JSONResponse({
        "task_id": task_id,
        "status": "queued",
        "queue_position": queue_pos,
    })


@app.get("/api/task/{task_id}")
@require_auth
async def api_task(request: Request, task_id: str):
    with _lock:
        task = _tasks.get(task_id)

    if not task:
        return JSONResponse({"error": "任务不存在"}, status_code=404)

    queue_pos = 0
    if task["status"] == "queued":
        with _lock:
            queued = [t for t in _tasks.values() if t["status"] == "queued"]
            queued.sort(key=lambda t: t["created_at"])
            for i, t in enumerate(queued):
                if t["task_id"] == task_id:
                    queue_pos = i + 1
                    break

    return JSONResponse({
        "task_id": task["task_id"],
        "status": task["status"],
        "queue_position": queue_pos,
        "progress": task["progress"],
        "logs": task["logs"][-30:],
        "result": task["result"],
        "error": task["error"],
    })


# 注册 auth 路由（必须在 static mount 之前）
register_auth_routes(app)

# 前端静态文件
app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    print("[启动] 海森堡抖音评论查询 — Web 后端")
    print("[启动] 浏览器打开 http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
