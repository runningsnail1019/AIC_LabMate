# 设备模板接入说明

日期：2026-10-12。分支：`feat/manual-device-templates`。本阶段在已完成的模板上接入网页与后端，不直接合并 `main`。

## 接入了什么

- `frontend/index.html`：新增可选设备模板、照片区域、参考图开关；显示真实 Qwen/模拟模式与本轮模板是否实际用于模型。切换设备时清空对话历史并更换会话 ID，防止跨设备沿用旧状态。
- `backend/app/main.py`：新增 `GET /api/device-templates`；`POST /api/analyze` 增加可选 `template_id`、`panel`、`include_references`。原参数仍可用。不选模板时保留原模型请求和知识库流程。
- 快模式调用 Qwen-VL 时加入部件目录、现场照片和相关说明书图；两步模式在视觉观察调用中使用同样模板，后续仍交给原规划器。
- `backend/device_templates/validation.py`：仅模板路径校验八字段观察 JSON、所选模板 ID、部件 ID、单图时间稳定性 unknown 与坐标范围/顺序。不合格的模型响应返回可解释的 502，而不是展示为有效识别。
- `backend/requirements.txt`：增加 `jsonschema`。模板模式扩大输出上限，快模式 3200，观察模式 2400；旧快模式仍为 650。
- `tests/test_template_integration.py`：无外部模型调用的集成检查。

未删除组长文件；仅为接入修改后端入口、网页和依赖列表，原工作流、知识库程序、数据库、模型配置文件及原启动脚本不改。未接专用 OCR，未训练 YOLO。

## 用户怎样用

1. 在此分支代码目录安装依赖、启动后端（已有运行环境也需补装新依赖）：

   ```powershell
   python -m pip install -r backend/requirements.txt
   python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
   ```

   也可使用原 `run_demo.ps1`，它要求原来配置的 Python 3.12 或可用的虚拟环境。已经运行旧服务器时必须重启；浏览器刷新页面。

2. 浏览器打开 `http://127.0.0.1:8000`。默认“不使用模板”，与旧调用兼容。选择对应设备后自动填入匹配知识库型号；API 也会拒绝所选模板与知识库型号冲突。
3. 选照片区域：前面板含屏幕、后面板、屏幕特写、多区域。默认附相关参考图；取消参考图开关可以试用文字模板，减少图像输入。
4. 上传当前实物照片并提问。结果里的“本轮模板”显示是否已用于模型请求；“查看视觉观察数据”能看到 `observations.components`。

前面板默认发送现场照片＋前面板参考页＋屏幕参考页；后面板/屏幕各附一张参考页；多区域附三张。模型必须先分析现场图，不能抄参考图读数。此阶段不会自动裁剪现场屏幕或检测选型。

## 重要限制

- 真正识别要求沿用原配置的有效 `QWEN_API_KEY`，且 `DEMO_MODE=false`。配置保存在本地 `backend/.env`，不提交密钥。未配置或演示模式只展示接口；模板模拟结果全部 unknown，不会向模型发送照片，不要将它算作准确率测试。
- 现场信号发生器 SDG2082X 可使用 SDG2000X 公共面板模板。现场示波器 SDS2202X Plus 没有对应模板，不可套用 SDS2000X HD，暂用“不使用模板”。SDM3055X-E 模板仅用于对应型号。
- 设备选择是用户输入，不是模型自动确认。API 会检查输入选择是否互相一致，但不保证照片确实是所选设备。
- 三份新手册未导入原知识库。模板请求只检索所填匹配型号的数据库证据，不回退到默认 EPI PDF；无证据时后端强制 `evidence_sufficient=false`。部件参考可帮助识别，但不能据此承诺完整操作指导。
- 参考图和部件输出会增加费用、响应时间及输出长度。本阶段不保证准确率提高，也不自动重试格式错误；应以真实照片做接入前后对比。
- 单张照片不能证明时间稳定、整个电路连接正确；黑屏不能读参数，模糊读数应返回 null。

## 接口示例与验证

`POST /api/analyze` 仍是 multipart 表单。除原 `image`、`question`、`version` 等字段，可传：

```text
version=SDG2000X          # 也接受目录明确列出的 SDG2082X
template_id=siglent_sdg2000x
panel=front             # front/rear/screen/all
include_references=true
```

返回保留原 state、decision、guidance 等字段，并增加 template 元数据（id/name/panel/applied/references_included）。演示模式 applied=false；applied=true 仅表示确实用于模型请求，不代表预测准确。

```powershell
python -m unittest discover -s tests -p 'test*.py' -v
```

检查覆盖原流程兼容、目录接口、现场/参考图顺序、参考图开关、快慢路径、误选拒绝、无匹配证据、图像质量门控、模拟模式、模板 JSON 和错误处理。模型响应在测试中被模拟，没有将现场照片发送给 Qwen，也没有完成真实识别准确率或 OCR 对比实验。

本阶段实际运行 23 项 Python 检查全部通过；另外运行 `node tests/test_frontend.mjs`，用独立 DOM/fetch 模拟验证网页目录加载、选型、提交字段、结果模式标记、会话清空和原流程恢复。此检查不是浏览器截图验收。

第一阶段 Word 交付说明保留为历史记录；本文件是接入阶段的补充说明。
