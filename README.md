# LabMate 电脑端 Demo

LabMate 是一个面向科研仪器操作指导的电脑端 MVP。用户在浏览器中上传仪器照片、填写问题和已选择的设备型号，后端会结合图片状态、对应说明书证据和最近对话，返回本轮可执行的指导。

当前版本支持：

- Qwen 多模态模型单次调用，同时完成现场观察和本轮规划；
- 图片压缩和 HTTP 连接复用，减少交互等待；
- 本地 SQLite + FTS5 知识库，按设备型号过滤说明书；
- 页码、章节、来源等级和 chunk 顺序等证据元数据；
- 普通问题、仪器操作、测量、故障排查和安全问题的轻量路由；
- 基于 SQLite 的会话检查点，支持后续多轮继续指导；
- 演示模式，无 API Key 也可以运行界面和完整链路。

## 目录结构

```text
backend/app/main.py                 FastAPI 接口和 Qwen 调用
backend/knowledge/import_manual.py  说明书导入和切片
backend/knowledge/retrieve.py       SQLite FTS5 检索和证据格式化
backend/workflow/engine.py          问题路由和会话检查点
frontend/index.html                 浏览器端 Demo
runtime/knowledge.db                本地知识库
run_demo.ps1                        Windows 启动脚本
```

`backend/.env`、`.venv`、运行时上传图片、会话数据库和 `third_party` 源码不会提交到 Git。

## 运行环境

- Windows PowerShell
- Python 3.12（推荐）
- 网络正常时才能调用 Qwen

在项目根目录执行：

```powershell
Set-Location 'D:\Users\legion\OneDrive\Desktop\AIC_Liu'
powershell -ExecutionPolicy Bypass -File .\run_demo.ps1
```

脚本会检查 `.venv` 是否存在：存在时使用虚拟环境安装依赖；不存在时使用系统 Python 3.12 安装依赖。启动后访问：

```text
http://127.0.0.1:8000
```

也可以临时放开当前 PowerShell 窗口的脚本权限后运行：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\run_demo.ps1
```

如果依赖已经安装，也可以直接启动：

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

## 配置 Qwen

复制示例配置：

```powershell
Copy-Item backend\.env.example backend\.env
```

然后编辑 `backend/.env`：

```ini
DEMO_MODE=false
QWEN_API_KEY=你的百炼API_KEY
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_FAST_MODEL=qwen-vl-plus
QWEN_VISION_MODEL=qwen-vl-max
QWEN_TEXT_MODEL=qwen-plus
QWEN_TRUST_ENV=false
FAST_MODE=true
KNOWLEDGE_PDF=EPI-EWB204+ 使用(1).pdf
```

交互模式建议保持 `FAST_MODE=true`。它用一次多模态请求完成观察和规划；设置为 `false` 会使用视觉分析和文本规划两次调用，适合调试，不适合日常演示。

如果网络必须使用系统代理，再设置 `QWEN_TRUST_ENV=true`，并确认系统代理地址可用。不要把 `backend/.env` 提交到 Git。

## 导入说明书知识库

第一次使用、替换说明书或修改设备型号后，执行：

```powershell
py -3.12 -m backend.knowledge.import_manual `
  'EPI-EWB204+ 使用(1).pdf' `
  --device-model 'EPI-EWB204+'
```

也可以写成一行：

```powershell
py -3.12 -m backend.knowledge.import_manual 'EPI-EWB204+ 使用(1).pdf' --device-model 'EPI-EWB204+'
```

导入结果保存在 `runtime/knowledge.db`。导入程序会读取 PDF、按页面和段落切分文本，并建立 FTS5 索引。检索时会使用用户填写的型号筛选对应内容，返回最多 5 条带页码和章节的证据。当前版本使用关键词/BM25 检索，尚未接入向量检索和 reranker。

## 使用逻辑

```text
浏览器上传图片 + 问题 + 设备型号
          ↓
图片压缩、问题路由、SQLite 证据检索
          ↓
Qwen 多模态观察和动态规划
          ↓
安全/图片质量检查
          ↓
指导文字、任务状态、证据和视觉观察返回前端
```

设备型号只用于选择知识库。系统默认上传图片就是目标设备现场，不会要求从图片中读取型号，也不会因为图片没有型号文字而拒绝回答。

问题路由只用于给模型提供问题类型提示，不会把用户强行限制在固定的示波器步骤中。当前包括：普通问题、仪器操作、测量与读数、故障排查、安全提醒。

## 接口

### `POST /api/analyze`

使用 `multipart/form-data`，字段如下：

```text
image       图片文件
question    用户问题
version     手动选择的设备型号/知识库标识
history     最近对话 JSON，可选
session_id  会话 ID，可选；前端会自动生成
```

返回内容包括：`guidance` 当前指导、`decision` 任务状态、`state` 视觉观察、`evidence` 结构化说明书证据、`route` 问题类型和 `session_id` 会话标识。

### `GET /api/health`

查看服务状态、当前模型配置、演示模式和快速模式是否开启。

## 常见问题

### PowerShell 禁止运行脚本

使用：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_demo.ps1
```

### 一直显示演示模式

检查 `backend/.env`：

```ini
DEMO_MODE=false
QWEN_API_KEY=你的API_KEY
```

修改后重启后端。

### Qwen 请求超时

依次检查模型名称、API 额度、网络连接和代理配置。交互演示建议使用 `qwen-vl-plus`，并保持 `FAST_MODE=true`。

### 知识库没有检索结果

确认网页填写的设备型号和导入命令中的 `--device-model` 完全一致，并重新执行说明书导入命令。

## 当前边界

当前版本适合做电脑端 Demo 和流程验证。知识库仍是 SQLite FTS5 关键词检索，文档解析以有文本层的 PDF 为主；后续可以在现有证据结构上增加向量检索、混合召回、OCR、reranker 和真正的 LangGraph `StateGraph`。
