# 设备照片识别模板

本目录完成第一项任务：以老师提供的三个 SIGLENT 说明书的面板图和部件说明制作可供 Qwen-VL 使用的模板。本次不接 OCR、不做 OCR 性能对比、不训练 YOLO，也不修改组长已有的后端、前端、知识库和工作流文件。

## 模板目录

| 模板 ID | 适用范围 | 前后面板和屏幕主要模块 |
|---|---|---|
| `siglent_sds2000x_hd` | 手册中的 SDS2000X HD 系列 | 屏幕、键盘、校准与接地、USB Host、MSO、模拟输入、电源、支撑脚；外触发、AUX、WaveGen、LAN、USB、电源、提手；菜单、网格、光标、通道、时基和触发参数 |
| `siglent_sdg2000x` | SDG2000X 系列，现场 SDG2082X 的公共面板 | 屏幕、USB、软键、数字键盘、旋钮、方向键、功能键、两通道输出；Counter、Aux、10MHz、地、LAN、USB、电源；波形预览、通道栏、参数、负载与输出、模式、菜单 |
| `siglent_sdm3055x_e` | SDM3055X-E 手册 | LCD、USB、软键、功能键、量程方向键、五个测量端子；电源、保险丝、交流电压选择器、巡检卡、LAN、USB、VMC、外触发；主副读数、测量功能、量程、触发和菜单 |

SDS2202X Plus 不是 SDS2000X HD 的选择别名。现场万用表只出现局部，无法核对其型号。详见 [照片核对记录](../../docs/device_templates_photo_notes.md)。

## 文件用途

- `templates/*.json`：部件 ID、中文名、手册标注、用途、位置提示、观察字段和出处。
- `assets/*/*.png`：9 张已检查的手册页参考图。保留页码和部件注释；不是现场状态。
- `prompts/common.md`：公共识别规则，约束 unknown、当前照片坐标、数值来源及静态图的判断边界。
- `prompts/generated/*.md`：从目录编译的三份可直接复制提示词，含用户问题占位符。
- `schemas/observation.schema.json`：供后续服务端校验的八字段观察协议。本次未接入旧 API 的强制校验。
- `examples/observation_unknown.json`：无法读取屏幕时的格式示例，不是模型测试结果。
- `catalog.py`：按模板 ID 读取、编译提示词、拼接现场照片和参考图。
- `__main__.py`：无网络的预览工具，不读取密钥、不调用模型。

## 直接使用

在仓库根目录运行，Python 3.10 以上，无需新增依赖：

```powershell
python -m backend.device_templates --list
python -m backend.device_templates --template-id siglent_sdg2000x --question "识别CH1输出和频率设定区域"
python -m backend.device_templates --template-id siglent_sdm3055x_e --panel rear --question "指出外触发和USB接口"
```

如果希望在百炼控制台手工试用，复制对应 `prompts/generated/*.md`，替换 `{用户问题}`，同时上传现场照片和对应参考图，分别标明“现场”和“参考”。优先只附相关面板图；黑屏时只做部件识别。

生成与原仓库 Qwen 调用兼容的请求对象（只打印，不发送）：

```powershell
python -m backend.device_templates --template-id siglent_sdg2000x --mode fast --image "C:\path\current.jpg" --question "请识别输出控制区"
```

默认前面板模式附前面板和屏幕参考图；`--panel rear` 只附后面板；`--no-reference-images` 可只保留文字目录。图像含 Base64，保存预览请求时注意文件大小，不要将现场请求数据提交到 Git。

## 与现有框架的接法

模板目前是独立、可选的新增组件。旧 `POST /api/analyze`、FAST_MODE、模型配置和 Demo 模式原样保留，启动旧 `run_demo.ps1` 不会自动启用模板。三份新手册也没有被导入旧 `knowledge.db`；不能声称已具备新设备完整操作指导。

后续接入只需要在原多模态 payload 的 `messages[0].content` 中使用本模块返回值：

```python
from backend.device_templates import build_visual_content

content = build_visual_content(
    template_id="siglent_sdg2000x",  # 独立于知识库 version，由应用明确选择
    image_bytes=model_bytes,
    content_type=model_content_type,
    question=question,
    mode="fast",                    # observation 模式对应旧 _qwen_vision
    manual_context=context,         # 仍使用匹配型号的检索证据
    history=history,
)
payload = {
    "model": QWEN_FAST_MODEL,
    "messages": [{"role": "user", "content": content}],
    "temperature": 0.1,
    "max_tokens": 1600,
}
```

这是接入示例，不是本次对旧主程序的改动。若要求返回多个部件，原 FAST_MODE 的 650 输出 token 可能不足，应按实际输出数量调整；本次没有改变旧配置。

`template_id` 是观察部件目录，`version` 是手册知识库标识，两者应明确配置。不要把 SDG 模板和 EPI 说明书一起当作操作证据；未找到匹配证据时保留 `evidence_sufficient=false`。

## 输出和来源的约定

外层沿用旧字段：`image_quality`、`observations`、`measurement_values`、`visible_text`、`uncertain_items`、`safety_flags`、`confidence`、`need_retake`。新增部件列表放在 `observations.components`，现有前端仍能显示它。

模板中的左右位置只是手册正视图的语义提示，不是固定像素坐标。模型返回 bbox 时必须定位当前照片，并用 [0,1] 归一化坐标；无法定位时返回 null。没有拍到不是“部件不存在”。模型自报置信度也不是经过校准的准确率。

单张照片不能证明波形或读数随时间稳定。`temporal_stability=unknown` 是单图协议约束。记录电缆“插在某个仪器端”也不能证明整条电路接对。

手册页码均同时记录 PDF 文件的 1 起始页号和印刷页号：SDS/SDG 的正文偏移为 2，SDM 的正文偏移为 12，前言罗马数字页另行标明。`assets/manifest.json` 给出原手册 SHA256、总页数、参考页来源，方便以后核对老师更换的手册版本。

## 检查

```powershell
python -m unittest discover -s tests -p test_device_templates.py -v
```

这些检查验证模板选择、图文顺序、部件来源、引用文件和 unknown 处理，不测量 Qwen/OCR 准确率。真实识别效果仍待接入后验证；本次未把照片发送到模型服务。
