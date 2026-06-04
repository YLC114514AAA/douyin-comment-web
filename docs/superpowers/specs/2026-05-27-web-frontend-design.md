# 海森堡抖音评论查询 — 网页前端版设计文档

## 1. 概述

将现有的桌面 GUI 版改造成网页版。用户通过浏览器访问网页，输入视频链接和目标用户，
后端调用现有爬虫核心进行爬取，结果传回前端渲染展示。

## 2. 架构

```
浏览器                    后端 (FastAPI)              爬虫核心
  │                          │                          │
  │  POST /api/crawl         │                          │
  │  {url, targets}          │                          │
  │ ─────────────────────►   │  生成 task_id            │
  │                          │  加入任务队列            │
  │  ◄─────────────────────  │  返回 {task_id}          │
  │                          │                          │
  │  GET /api/task/{id}      │                          │
  │ ─────────────────────►   │  返回状态/进度/结果      │
  │  ◄─────────────────────  │                          │
  │                          │                          │
  │  (轮询 2秒一次)           │  ThreadPoolExecutor     │
  │  (直到 status=done)      │  └─ crawler.crawl()     │
  │                          │     └─ output.filter()  │
  │                          │        └─ 存结果         │
```

## 3. 后端 API 设计

### 3.1 POST /api/crawl

请求体：
```json
{
  "url": "https://v.douyin.com/xxx/...",
  "targets": "不hh, 张三"
}
```

返回：
```json
{
  "task_id": "TK-20260527-001",
  "status": "queued"
}
```

### 3.2 GET /api/task/{task_id}

返回：
```json
{
  "task_id": "TK-20260527-001",
  "status": "queued | running | done | failed",
  "queue_position": 1,
  "progress": {"parent_total": 50, "replies_done": 10, "replies_total": 15},
  "logs": ["[信息] 开始爬取...", "[进度] 一级评论: 50条"],
  "result": { ... },    // status=done 时存在
  "error": "..."        // status=failed 时存在
}
```

## 4. 并发模型

```
ThreadPoolExecutor(max_workers=2)
  ├── Worker 1 ── 任务A (运行中)
  ├── Worker 2 ── 任务B (运行中)
  └── Queue ──── 任务C, 任务D... (排队)
```

- 最多同时 2 个爬虫
- 超过排队，前端实时显示排队位置
- 爬虫 print 输出通过 StringIO 捕获 → 写入任务对象的 logs 列表

## 5. 前端页面 (static/index.html)

### 5.1 页面结构

```
┌────────────────────────────────────────┐
│     海森堡抖音评论查询                 │
│     输入视频链接 + 目标用户，即搜即得   │
├────────────────────────────────────────┤
│  视频链接: [_______________________]   │
│  目标用户: [_______________________]   │
│  [开始查询]                            │
├────────────────────────────────────────┤
│  状态: 排队中... (前面还有 2 人)        │
│  [日志区，实时滚动]                     │
├────────────────────────────────────────┤
│  [结果区，彩色渲染，仿GUI风格]          │
│    - 金色背景标记目标用户               │
│    - 树线展示层级                       │
│    - 圆圈序号 ①②③                     │
│    - 图片链接 [查看图片] 可点击         │
└────────────────────────────────────────┘
```

### 5.2 技术选型

- 纯 HTML + CSS + JS，无框架，单文件
- CSS 暗色主题（#1a1a2e 底色，和 GUI 色调一致）
- JS fetch API 调后端，setInterval 轮询
- 结果区用 DOM 操作动态生成

## 6. 文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `server.py` | 新增 | FastAPI 后端入口，API 路由 + 任务管理 |
| `static/index.html` | 新增 | 前端页面 |
| `requirements.txt` | 修改 | 追加 fastapi, uvicorn |
| 其他现有文件 | 不动 | crawler.py, output.py, sign.py, douyin.js, config.py |

## 7. 启动方式

```bash
pip install fastapi uvicorn
python server.py
# 浏览器打开 http://localhost:8000
```

## 8. 边界情况

- 提交时前端校验：URL 和 targets 不能为空
- 任务超时：单个任务最多跑 5 分钟，超时自动终止
- 任务清理：完成后保留 10 分钟，之后从内存删除
- 重复提交：不做限制，每次提交都是独立任务
- 后端挂掉：前端轮询失败后显示"连接断开，请刷新"
