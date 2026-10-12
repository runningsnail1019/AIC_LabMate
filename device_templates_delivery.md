# LabMate 设备视觉模板交付说明

> 本文和同名 Word 是第一阶段“模板制作”交付记录，下面的未接入/未上传描述保留为当时状态。后续已上传，并按用户追加要求接入前后端；当前功能、使用方法与验证范围请看 [设备模板接入说明](device_templates_integration.md)。

日期：2026-10-12。基准：`main` 提交 `0771203e93d725b63bbe092194e1c8cfcc30cb4c`。新增分支：`feat/manual-device-templates`。

## 本次完成的工作

完成第一项任务，建立三个基于说明书的设备视觉模板，合计 105 个部件或功能区条目。条目粒度包括部件组与子部件，不是 105 个独立硬件。

| 模板 | 条目数 | 来源及页码 |
|---|---:|---|
| SDS2000X HD 示波器 | 34 | 前面板 PDF22/印刷20；后面板 PDF23/印刷21；屏幕 PDF27/印刷25；控制区 PDF40至44/印刷38至42 |
| SDG2000X 信号发生器 | 32 | 前面板 PDF10/印刷8；后面板 PDF11/印刷9；屏幕 PDF12至13/印刷10至11；功能按键 PDF18、20、21 |
| SDM3055X-E 万用表 | 39 | 前面板 PDF16/印刷4；后面板 PDF17/印刷5；界面 PDF19/印刷7；功能按键 PDF22/印刷10；量程 PDF23/印刷11 |

每个条目包含机器可读 ID、中文名称、面板类别、手册图标记、位置提示、用途、观察项、手册章节与双页码。已检查三份手册的前后面板和界面图，并将 9 张参考页图放入模板目录。

同时制作了公共提示词、三份可复制的完整提示词、输出 JSON Schema、无法读取时的 JSON 示例，以及按模板构造 Qwen 多图请求内容的工具。只生成请求数据，不自动调用模型。

## 仓库新增文件

```text
backend/device_templates/
  __init__.py
  __main__.py                         本地预览命令
  catalog.py                          模板读取和Qwen输入拼接
  README.md                           使用及接入说明
  templates/                          三份设备部件目录JSON
  assets/                             九张手册页图和来源manifest
  prompts/common.md                   公共识别规则
  prompts/generated/                  三份编译后的完整提示词
  schemas/observation.schema.json     输出协议
  examples/observation_unknown.json   不可读时的示例
docs/device_templates_photo_notes.md  现场照片核对记录
docs/device_templates_delivery.md     本说明
docs/device_templates_delivery.docx   Word说明
tests/test_device_templates.py        无网络检查
```

组长原有 `backend/app/main.py`、前端、工作流、知识库程序、数据库、README、说明书、PPT 和启动脚本均保留。没有修改或删除原文件。

## 如何使用

在仓库根目录执行 `python -m backend.device_templates --list` 查看可选模板。

例如：

```powershell
python -m backend.device_templates --template-id siglent_sdg2000x --question "请识别CH1输出区域"
python -m backend.device_templates --template-id siglent_sdm3055x_e --panel rear --question "请指出外触发接口"
python -m backend.device_templates --template-id siglent_sdg2000x --mode fast --image "C:\path\current.jpg"
```

前两条打印识别提示词；第三条构造现有 Qwen 消息格式的 JSON 请求，不发送网络请求。也可以把 `prompts/generated` 中的提示词复制到多模态模型控制台，替换用户问题，并将现场照片和手册参考图分别标记。

## 与现有框架的关系

本次模板是可选新增模块，旧 `/api/analyze` 不会自动调用它。模板工具提供 `build_visual_content()`，后续可替换原多模态请求的 content 构造部分。FAST_MODE 中原有 observation 和 plan 外层协议保留，观察模式兼容旧 `_qwen_vision`。前端能继续用原来的视觉数据展示。

没有导入三份新手册到旧知识库，也没有替换动态规划器。模板 ID 与知识库 version 分别配置；新增部件目录不能当作操作 SOP。接入时需要保证检索证据来自相应设备，不能回退使用 EPI 手册作为 SIGLENT 操作依据。

## 照片核对和观察边界

实物示波器是 SDS2202X Plus，而手册是 SDS2000X HD。HD 模板没有把 Plus 作为别名，避免四通道 HD 面板套到两通道 Plus。已将 Plus 照片中能读到的部件名称另记，未推断后面板或专属操作。SDG2082X 的公共面板可采用 SDG2000X 系列模板，但不迁移示例机的带宽或采样率。照片中未完整出现 SDM3055X-E，不能据照片上方另一台万用表的局部端子验证它。

提示词明确：手册图只能帮助命名和定位，手册示例读数不能视为现场读数；单张图的时间稳定性为 unknown；未拍后面板不是部件不存在；只看到仪器端插线不能证明电路接对；旋钮外观不表示具体参数。bbox 必须在当前照片中重新定位，不能复制手册图坐标。

## 已完成的检查

七项无网络测试通过，覆盖目录和引用文件完整性、误选型号拒绝、现场图与参考图的顺序、后面板范围、只用文字模板、FAST_MODE 协议以及 unknown 示例。三份目录、Schema 和示例 JSON 均可解析；参考页图已目视核对，Word 说明完成后另做分页检查。

这些检查验证模板文件和输入构造，不是 Qwen 实际准确率测试。未调用模型服务，未接入或评估 OCR，未训练检测器，也未增加固定任务状态机。

本地分支已提交全部新增文件。推送检查显示当前 Git 没有可用的 GitHub 登录凭据，远程分支尚未上传，也未合并至 main。完成 GitHub 登录并具备该仓库写入权限后，可以推送这个新增分支。另提供只含新增文件的 ZIP，便于组长核对和接收。
