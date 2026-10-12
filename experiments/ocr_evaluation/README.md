# 仪器屏幕 OCR 有限样本实验

本目录仅是第二项任务的独立实验，不改变现有 demo 的模型调用，不把 OCR 默认接入生产路径。没有用模拟 Qwen 输出作为识别成绩。

使用现有 4 张实拍、3 张说明书页中的 4 个屏幕区域，共 7 个源图、8 个区域。原始照片、处理图、模型权重和逐行 OCR 输出留在本机；`runtime/ocr_eval_local/` 已加入忽略规则。

## 运行

在独立 Python 3.12 虚拟环境安装本目录 `requirements.txt`，不要改变原 demo 环境。在仓库根目录执行：

```powershell
python experiments/ocr_evaluation/prepare.py
python experiments/ocr_evaluation/audit_regions.py
python -m unittest discover -s experiments/ocr_evaluation -p test_scoring.py -v
python experiments/ocr_evaluation/run_ocr.py --model-size server --repeat 1
python experiments/ocr_evaluation/score.py --model-size server
python experiments/ocr_evaluation/run_ocr.py --model-size mobile --repeat 1
python experiments/ocr_evaluation/score.py --model-size mobile
python experiments/ocr_evaluation/export_results.py
```

RapidOCR 首次初始化会下载公开模型，不上传输入图像。本实验明确选择 PP-OCRv5 server 检测和识别，不使用 RapidOCR 默认 PP-OCRv4。CPU 四线程，无透视校正、阈值化、专门屏幕微调或 OCR 后纠错；识别与文本框阈值均为 0.5。整图和屏幕裁剪分别最长边 1800、JPEG quality 84，与现有应用压缩策略一致。人工裁剪并非自动检测，不能据此宣称已开发自动裁剪功能。

`--repeat 1` 每种输入实测一次；耗时仅为该次本机观测值，不是稳定服务时延或云模型对比。可以增加次数，但多次运行同一张图不能增加独立样本量。

## 评分边界

`cases.json` 是助手在查看 OCR 输出前直接目视原图建立的字段文本及区域参考标注，未由人员独立复核，不能视为正式人工金标准。主指标为指定区域内数值和单位关键字符串的严格召回。归一化只去空白、统一 Unicode 等价形式和 μs/us；保留小数、正负号、大小写敏感的单位前缀和不等号。显式正号丢失也计严格字符串不匹配，这不一定意味着数值符号被反转。此指标不是完整字段提取准确率，不测试上下文理解或波形判断。

字符串必须在对应区域的 OCR 文本中出现。垂直重叠的文字框按左右顺序拼接，容纳数字、正号、单位被拆成不同框的情况；对不同行保留分隔，不把两个不同读数直接拼成一个。重叠判定用于容纳合并文本行，不证明模型已正确关联通道/字段。副读数、光标倒数、触发计数器分开标注。

两个开机画面与一个黑屏用作负样本，分别记录数字片段及形如数值加单位的误检。OCR 检出品牌不是有效读数；没有有单位的伪读数也不代表完全没有数字误检或其他场景均无幻觉。

手册页上的文字、红箭头、字母标注与实拍不同。万用表单显/双显来自同一页，不是两个独立实拍。参考标注未经人员复核；样本很小，不能给出总体准确率或统计显著性。

## Qwen 对比状态

现有默认快模型为 `qwen-vl-plus`，慢模式视觉模型为 `qwen-vl-max`，但本机应用健康检查显示没有配置 Qwen 密钥。整图 Qwen、屏幕裁剪 Qwen、Qwen+OCR 三组均未运行；不得填写估计成绩，不得用说明书文本层抽取代替图像识别。没有运行这些组之前，无法实证断言“专用 OCR 比现有模型更好/更差”。
