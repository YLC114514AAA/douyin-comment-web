# 海森堡网页前端版 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有桌面 GUI 版改造成网页版：FastAPI 后端 + 纯 HTML 前端，多用户任务排队

**Architecture:** 前端 POST /api/crawl 提交任务拿 task_id → setInterval 2s 轮询 GET /api/task/{id} → 后端 ThreadPoolExecutor(2) 串行爬取 → 结果回传前端渲染

**Tech Stack:** Python 3.12, FastAPI, uvicorn, HTML+CSS+JS (无框架)

---

### Task 1: 更新 requirements.txt 并安装依赖

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: 追加 fastapi 和 uvicorn**

```python
# requirements.txt 尾部追加
fastapi>=0.100.0
uvicorn>=0.23.0
```

- [ ] **Step 2: 安装依赖**

Run: `pip install fastapi uvicorn -q`

- [ ] **Step 3: 验证安装**

Run: `python -c "from fastapi import FastAPI; import uvicorn; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "chore: 追加 fastapi uvicorn 依赖"
```

---

### Task 2: 新增 server.py — 任务管理核心

**Files:**
- Create: `server.py`

- [ ] **Step 1: 创建 server.py 骨架 — 导入 + app + 路由占位**

```python
"""
海森堡抖音评论查询 — Web 后端
FastAPI + ThreadPoolExecutor 任务队列
"""

import json
import io
import os
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, Future
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

# 把项目根目录加入 sys.path，保证 import 爬虫模块正常
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crawler import DouyinCommentCrawler
from output import filter_by_douyin_id

app = FastAPI(title="海森堡抖音评论查询")

# 任务存储: {task_id: TaskDict}
_tasks: dict[str, dict] = {}
_executor = ThreadPoolExecutor(max_workers=2)
_lock = threading.Lock()


# ======================== 路由 ========================

@app.post("/api/crawl")
async def api_crawl(request: Request):
    pass  # Task 3 实现


@app.get("/api/task/{task_id}")
async def api_task(task_id: str):
    pass  # Task 4 实现


# 前端静态文件
app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    print("[启动] 海森堡抖音评论查询 — Web 后端")
    print("[启动] 浏览器打开 http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

- [ ] **Step 2: 验证语法**

Run: `python -m py_compile server.py`
Expected: 无输出（编译通过）

- [ ] **Step 3: 验证启动**

Run: `timeout 3 python server.py 2>&1 || true`
Expected: 看到 `[启动] 海森堡抖音评论查询 — Web 后端`

- [ ] **Step 4: Commit**

```bash
git add server.py
git commit -m "feat: server.py 骨架 — FastAPI + 任务框架"
```

---

### Task 3: 实现 POST /api/crawl 路由

**Files:**
- Modify: `server.py`

- [ ] **Step 1: 实现 api_crawl 路由 + _enqueue_task 辅助函数**

在 `server.py` 的 `_lock` 定义之后，路由定义之前插入：

```python
def _enqueue_task(url: str, targets: list[str]) -> str:
    """创建任务并入队"""
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

    # 提交到线程池
    _executor.submit(_run_crawl_task, task_id, url, targets)
    return task_id
```

替换 `api_crawl` 占位为：

```python
@app.post("/api/crawl")
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

    # 计算排队位置
    with _lock:
        pos = sum(1 for t in _tasks.values() if t["status"] == "queued")

    return JSONResponse({
        "task_id": task_id,
        "status": "queued",
        "queue_position": pos,
    })
```

- [ ] **Step 2: 实现 _run_crawl_task 执行体**

在 `server.py` 的 `_enqueue_task` 之后插入：

```python
def _run_crawl_task(task_id: str, url: str, targets: list[str]):
    """后台线程执行爬取任务"""
    with _lock:
        _tasks[task_id]["status"] = "running"

    # 重定向 print 到 logs
    log_buffer = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = log_buffer

    crawler = None
    try:
        crawler = DouyinCommentCrawler(headless=False)
        video_url, api_comments, dom_comments = crawler.crawl(url)

        # 选数据源
        all_comments = api_comments if api_comments else dom_comments
        total_replies = sum(len(c.get("replies") or []) for c in all_comments)

        with _lock:
            _tasks[task_id]["progress"]["parent_total"] = len(all_comments)
            _tasks[task_id]["progress"]["replies_total"] = total_replies

        if not all_comments:
            with _lock:
                _tasks[task_id]["status"] = "done"
                _tasks[task_id]["result"] = {"matched": [], "video_url": video_url}
            return

        # 筛选
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
            _tasks[task_id]["status"] = "done"
            _tasks[task_id]["result"] = result

    except Exception as e:
        with _lock:
            _tasks[task_id]["status"] = "failed"
            _tasks[task_id]["error"] = str(e)

    finally:
        sys.stdout = old_stdout
        # 收集 captured logs
        captured = log_buffer.getvalue()
        lines = [l.strip() for l in captured.splitlines() if l.strip()]
        with _lock:
            _tasks[task_id]["logs"].extend(lines)
        log_buffer.close()
        if crawler:
            try:
                crawler.close()
            except Exception:
                pass
```

- [ ] **Step 3: 验证编译**

Run: `python -m py_compile server.py`
Expected: 无输出

- [ ] **Step 4: Commit**

```bash
git add server.py
git commit -m "feat: POST /api/crawl + 后台爬取任务执行"
```

---

### Task 4: 实现 GET /api/task/{task_id} 路由

**Files:**
- Modify: `server.py`

- [ ] **Step 1: 替换 api_task 占位**

```python
@app.get("/api/task/{task_id}")
async def api_task(task_id: str):
    with _lock:
        task = _tasks.get(task_id)

    if not task:
        return JSONResponse({"error": "任务不存在"}, status_code=404)

    # 计算排队位置
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
        "logs": task["logs"][-30:],  # 只返回最近30条
        "result": task["result"],
        "error": task["error"],
    })
```

- [ ] **Step 2: 验证编译**

Run: `python -m py_compile server.py`
Expected: 无输出

- [ ] **Step 3: Commit**

```bash
git add server.py
git commit -m "feat: GET /api/task/{id} — 任务状态查询"
```

---

### Task 5: 新增前端页面 static/index.html

**Files:**
- Create: `static/index.html`

- [ ] **Step 1: 创建 HTML + CSS 骨架**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>海森堡抖音评论查询</title>
<style>
  body {
    background: #1a1a2e;
    color: #e0e0e0;
    font-family: "Microsoft YaHei UI", "微软雅黑", sans-serif;
    max-width: 900px;
    margin: 0 auto;
    padding: 20px;
  }
  h1 { color: #FFD700; text-align: center; margin-bottom: 4px; }
  .subtitle { color: #888; text-align: center; font-size: 13px; margin-bottom: 24px; }
  .card {
    background: #16213e;
    border: 1px solid #2a2a4a;
    border-radius: 8px;
    padding: 20px;
    margin-bottom: 16px;
  }
  input, textarea {
    width: 100%;
    background: #0f0f23;
    border: 1px solid #2a2a4a;
    color: #e0e0e0;
    padding: 10px;
    border-radius: 4px;
    font-size: 14px;
    box-sizing: border-box;
    margin-bottom: 12px;
  }
  input:focus { outline: none; border-color: #FFD700; }
  button {
    background: #FFD700;
    color: #1a1a2e;
    border: none;
    padding: 10px 32px;
    border-radius: 6px;
    font-size: 15px;
    font-weight: bold;
    cursor: pointer;
  }
  button:hover { background: #FFC107; }
  button:disabled { background: #555; cursor: not-allowed; }
  #status { color: #4FC3F7; font-size: 13px; margin-top: 12px; }
  #logs {
    background: #0f0f23;
    border-radius: 6px;
    padding: 14px;
    max-height: 200px;
    overflow-y: auto;
    font-family: Consolas, monospace;
    font-size: 12px;
    color: #aaa;
    white-space: pre-wrap;
    margin-top: 10px;
  }
  .result-comment { margin-bottom: 14px; }
  .target-highlight { background: #5A4500; padding: 2px 6px; border-radius: 3px; }
  .tree-line { color: #00CED1; font-weight: bold; }
  .user-name { color: #87CEEB; font-weight: bold; }
  .likes { color: #FF6B6B; font-weight: bold; }
  .time-ip { color: #888; font-size: 12px; }
  .comment-text { color: #e0e0e0; margin: 4px 0 0 20px; }
  .level-tag { color: #666; font-size: 10px; }
  .arrow-mark { color: #FF8C00; font-weight: bold; }
  .separator { color: #555; }
  .summary { font-size: 14px; font-weight: bold; color: #fff; }
  .stat { color: #4FC3F7; }
  .error { color: #FF6B6B; }
</style>
</head>
<body>

<h1>海森堡抖音评论查询</h1>
<p class="subtitle">输入视频链接 + 目标用户，即搜即得 — 支持分享文案、抖音号、UID、昵称</p>

<div class="card">
  <input type="text" id="urlInput" placeholder="粘贴抖音分享文案或视频链接...">
  <input type="text" id="targetsInput" placeholder="目标用户（抖音号/UID/昵称，逗号分隔，如 不hh, 张三）">
  <button id="submitBtn" onclick="submitTask()">开始查询</button>
  <div id="status"></div>
</div>

<div id="logs" style="display:none;"></div>

<div id="result"></div>

<script>
// —— 将在 Task 6 填充 JS 逻辑 ——
</script>

</body>
</html>
```

- [ ] **Step 2: 验证页面可打开**

Run: `python -c "import os; os.chdir('C:/Users/Administrator/Desktop/ylc114514'); print(open('static/index.html','r',encoding='utf-8').read()[:50])"`
Expected: `<!DOCTYPE html>`

- [ ] **Step 3: Commit**

```bash
git add static/index.html
git commit -m "feat: 前端页面 HTML+CSS 骨架"
```

---

### Task 6: 前端 JS 逻辑 — 提交任务 + 轮询 + 结果渲染

**Files:**
- Modify: `static/index.html`

- [ ] **Step 1: 添加提交与轮询 JS**

把 HTML 中的 `<script>` 注释替换为：

```javascript
const API = "";
let pollTimer = null;

async function submitTask() {
  const url = document.getElementById("urlInput").value.trim();
  const targets = document.getElementById("targetsInput").value.trim();
  if (!url) { alert("请输入视频链接"); return; }
  if (!targets) { alert("请输入目标用户"); return; }

  document.getElementById("submitBtn").disabled = true;
  document.getElementById("status").innerText = "正在提交...";
  document.getElementById("result").innerHTML = "";
  document.getElementById("logs").style.display = "none";

  try {
    const resp = await fetch(API + "/api/crawl", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({url, targets})
    });
    const data = await resp.json();
    if (data.error) { alert(data.error); resetBtn(); return; }
    document.getElementById("status").innerText = "任务已提交，排队中...";
    pollTimer = setInterval(() => pollTask(data.task_id), 2000);
  } catch (e) {
    document.getElementById("status").innerText = "连接失败，请检查后端是否启动";
    resetBtn();
  }
}

async function pollTask(taskId) {
  try {
    const resp = await fetch(API + "/api/task/" + taskId);
    if (!resp.ok) { document.getElementById("status").innerText = "轮询失败"; return; }
    const data = await resp.json();

    // 状态
    let st = "";
    if (data.status === "queued") st = `排队中 (前面还有 ${data.queue_position} 人)...`;
    else if (data.status === "running") st = "正在爬取...";
    else if (data.status === "done") st = "完成！";
    else if (data.status === "failed") st = "失败: " + (data.error || "");
    document.getElementById("status").innerText = st;

    // 日志
    if (data.logs && data.logs.length > 0) {
      document.getElementById("logs").style.display = "block";
      document.getElementById("logs").innerText = data.logs.join("\n");
    }

    // 结果
    if (data.status === "done" && data.result) {
      clearInterval(pollTimer);
      renderResult(data.result);
      resetBtn();
    }
    if (data.status === "failed") {
      clearInterval(pollTimer);
      resetBtn();
    }
  } catch (e) {
    document.getElementById("status").innerText = "连接断开，请刷新";
    clearInterval(pollTimer);
    resetBtn();
  }
}

function resetBtn() {
  document.getElementById("submitBtn").disabled = false;
}
```

- [ ] **Step 2: 添加结果渲染函数**

在 `resetBtn` 之后追加：

```javascript
const CIRCLE = ["①","②","③","④","⑤","⑥","⑦","⑧","⑨","⑩",
                "⑪","⑫","⑬","⑭","⑮","⑯","⑰","⑱","⑲","⑳"];

function renderResult(data) {
  const container = document.getElementById("result");
  let html = '<div class="card">';

  // 头部
  html += '<div class="summary">◆ 海森堡抖音评论查询结果</div>';
  html += '<div class="separator">' + "─".repeat(48) + '</div>';
  let targets = (data.targets || []).join(", ");
  html += `<div><span class="summary">视频</span> <span class="time-ip">${esc(data.video_url||"")}</span></div>`;
  html += `<div><span class="summary">时间</span> ${esc(data.scraped_at||"")}</div>`;
  html += `<div><span class="summary">查询</span> ${esc(targets)}</div>`;
  let likes = 0;
  let circleIdx = -1;
  for (let c of (data.comments || [])) {
    if (isTarget(c, data.targets || [])) { likes += c.digg_count || 0; assignCircle(c); }
    for (let r of (c.replies || [])) {
      collectCircle(r);
      if (isTarget(r, data.targets || [])) likes += r.digg_count || 0;
    }
  }
  let totalItems = circleIdx + 1;
  html += `<div><span class="summary">目标用户评论总点赞数</span> <span class="likes">${likes}</span></div>`;

  // 评论区
  for (let c of (data.comments || [])) {
    html += renderComment(c, data.targets || [], "");
  }

  html += `<div class="summary">◆ 目标用户共发 ${totalItems} 条评论，总点赞数 ${likes}</div>`;
  html += '</div>';
  container.innerHTML = html;
}

let _circleIdx = -1;
let _circleMap = {};

function assignCircle(c) { _circleIdx++; if (_circleIdx < CIRCLE.length) _circleMap[c.cid] = CIRCLE[_circleIdx]; }
function collectCircle(c) {
  _circleIdx++;
  if (_circleIdx < CIRCLE.length) _circleMap[c.cid] = CIRCLE[_circleIdx];
  for (let r of (c.replies || [])) collectCircle(r);
}
function getCircle(cid) { return _circleMap[cid] || ""; }

function isTarget(c, targets) {
  let tSet = new Set(targets.map(t => t.toLowerCase()));
  return !![c.unique_id, c.uid, c.short_id, c.nickname].filter(Boolean).some(
    v => tSet.has(String(v).toLowerCase())
  );
}

function renderComment(c, targets, indent) {
  let me = isTarget(c, targets);
  let hl = me ? ' target-highlight' : '';
  let arrow = me ? ' <span class="arrow-mark">◀</span>' : '';
  let circle = getCircle(c.cid);

  let s = '<div class="result-comment' + hl + '">';
  s += '<span class="likes">❤ ' + (c.digg_count||0) + '</span> ';
  s += '<span class="time-ip">' + fmtTime(c.create_time) + ' IP:' + (c.ip_label||'-') + '</span>';
  if (circle) s += ' <span style="color:#FFA500;font-weight:bold">' + circle + '</span>';
  s += '<span class="level-tag"> · 一级评论</span>' + arrow;
  s += '<div class="comment-text">' + esc(c.text||'') + '</div>';

  // 图片
  let media = (c.images||[]).concat(c.stickers||[]);
  if (media.length > 0) {
    s += '<div style="margin-left:20px"><span class="time-ip">[查看图片 (' + media.length + '张)]</span></div>';
  }

  // 回复
  for (let i = 0; i < (c.replies||[]).length; i++) {
    let r = c.replies[i];
    let last = i === c.replies.length - 1;
    s += renderReply(r, targets, indent, last, 1);
  }
  s += '</div>';
  return s;
}

function renderReply(r, targets, indent, isLast, depth) {
  let me = isTarget(r, targets);
  let hl = me ? ' target-highlight' : '';
  let arrow = me ? ' <span class="arrow-mark">&#9654;</span>' : '';
  let circle = getCircle(r.cid);
  let branch = isLast ? "└── " : "├── ";
  let cont = isLast ? "    " : "│   ";

  let s = '<div class="' + hl + '">';
  s += '<span class="tree-line">' + indent + branch + '</span>';
  s += '<span class="user-name">' + esc(r.nickname||"???") + '</span> ';
  s += '<span class="likes">❤ ' + (r.digg_count||0) + '</span> ';
  s += '<span class="time-ip">' + fmtTime(r.create_time) + '</span>';
  if (circle) s += ' <span style="color:#FFA500;font-weight:bold">' + circle + '</span>';
  s += '<span class="level-tag"> · 二级评论</span>' + arrow;
  s += '<div class="comment-text">' + esc(r.text||'') + '</div>';

  let media = (r.images||[]).concat(r.stickers||[]);
  if (media.length > 0) {
    let link = '[查看图片 (' + media.length + '张)]';
    s += '<div style="margin-left:20px"><span class="time-ip">' + link + '</span></div>';
  }

  for (let i = 0; i < (r.replies||[]).length; i++) {
    let sub = r.replies[i];
    let subLast = i === r.replies.length - 1;
    s += renderReply(sub, targets, indent + cont, subLast, depth + 1);
  }
  s += '</div>';
  return s;
}

function fmtTime(ts) {
  if (!ts) return "未知";
  let d = new Date(ts * 1000);
  return d.getFullYear() + "-" + String(d.getMonth()+1).padStart(2,"0") + "-" +
         String(d.getDate()).padStart(2,"0") + " " +
         String(d.getHours()).padStart(2,"0") + ":" +
         String(d.getMinutes()).padStart(2,"0");
}

function esc(s) {
  return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}
```

- [ ] **Step 2: 验证前端完整可加载**

Run: `python -c "print(len(open('C:/Users/Administrator/Desktop/ylc114514/static/index.html','r',encoding='utf-8').read()))"`
Expected: 大于 5000

- [ ] **Step 3: Commit**

```bash
git add static/index.html
git commit -m "feat: 前端 JS — 提交轮询 + 结果渲染"
```

- [ ] **Step 4: 端到端验证**

```bash
# 终端1: 启动后端
python server.py
# 终端2: 浏览器打开 http://localhost:8000
# 输入视频链接和目标用户 → 提交 → 观察排队 → 日志 → 结果渲染
```

确认：
- [ ] 页面加载后能看到标题和输入框
- [ ] 提交后能看到排队状态
- [ ] 爬虫运行期间能看到日志滚动
- [ ] 完成后结果正确渲染（树线、金色标记、序号、层级标签）
- [ ] 再开一个浏览器标签提交第二个任务，验证排队机制

- [ ] **Step 5: Commit**

```bash
git add server.py static/index.html
git commit -m "feat: 端到端验证通过"
```
