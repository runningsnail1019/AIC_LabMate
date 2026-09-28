# LabMate 电脑端 Demo

这是一个最小可运行闭环：浏览器上传仪器图片、输入问题和设备版本号，Python 后端调用 Qwen（或演示模式），读取设备说明书，经过状态机判断后返回指导文字。

## 运行

PowerShell 执行：

```powershell
Set-Location 'D:\Users\legion\OneDrive\Desktop\AIC_Liu'
.\run_demo.ps1
```

首次启动会创建 `.venv` 并安装依赖，然后访问 `http://127.0.0.1:8000`。

默认是演示模式，不需要 Qwen Key。要接入 Qwen：

也可以复制 `backend/.env.example` 为 `backend/.env`，填入 Key 并将 `DEMO_MODE` 改为 `false`。

```powershell
$env:DEMO_MODE='false'
$env:QWEN_API_KEY='你的Key'
$env:QWEN_BASE_URL='https://dashscope.aliyuncs.com/compatible-mode/v1'
$env:QWEN_VISION_MODEL='qwen-vl-max'
$env:QWEN_TEXT_MODEL='qwen-plus'
.\run_demo.ps1
```

后端接口为 `POST /api/analyze`，接收 multipart 字段：`image`、`question`、`version`。目前知识库默认读取项目根目录的 `EPI-EWB204+ 使用(1).pdf`，以后可以替换为按设备版本号选择的 PDF 或向量库。

当前知识库第一阶段已经支持本地 SQLite FTS5 索引。首次导入设备手册：

```powershell
py -3.12 -m backend.knowledge.import_manual 'EPI-EWB204+ 使用(1).pdf' --device-model 'EPI-EWB204+'
```

导入后，后端会优先按设备型号从 `runtime/knowledge.db` 检索带页码的证据；尚未导入时才回退到 PDF 关键词扫描。后续可以在这个稳定的元数据和证据层之上接入向量检索与重排序。

交互默认启用 `FAST_MODE=true`：一次 Qwen-VL 调用同时返回视觉观察和本轮规划，减少一次模型往返。将其改为 `false` 可恢复旧的“两次模型调用”调试模式。

快速模式使用 `QWEN_FAST_MODEL`（默认 `qwen-vl-plus`）；高质量复核模式仍可使用 `QWEN_VISION_MODEL=qwen3.8-max`。如果百炼控制台中的模型 ID 不同，以控制台 API 示例为准。

如果请求长时间超时，先检查电脑的 HTTP 代理设置。Demo 默认不读取系统代理；若你的网络必须经过代理，在 `backend/.env` 中设置 `QWEN_TRUST_ENV=true`，并确保代理地址确实可用。
