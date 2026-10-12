# 现场照片核对记录

2026-10-12。本记录只作人工核对，没有调用 Qwen，没有进行 OCR 对比。现场照片不上传到仓库，避免带入实验室人员及背景信息。

| 用户提供的照片 | 能人工确认的内容 | 对模板的影响 |
|---|---|---|
| 微信图片_20261012170118_139_2.jpg | 铭牌为 SDS2202X Plus；前面板两个模拟输入，右侧控制区，屏幕为 SIGLENT 开机画面 | 不选 SDS2000X HD 模板；开机阶段不读频率或峰峰值 |
| 微信图片_20261012170127_140_2.jpg | 同一 Plus 设备，CH1/CH2 接口有线，屏幕仍是开机画面 | 只确认仪器端插接，不能认定被测端或地线正确 |
| 微信图片_20261012170137_141_2.jpg | 信号发生器为 SDG2082X，前面板布局与 SDG2000X 手册相近，屏幕黑屏，两个输出端有线 | 系列模板可供人工选择；不从手册复制幅值或 ON 状态 |
| 微信图片_20261012170145_142_2.jpg | Plus 显示测量菜单和光标；C1/C2 通道参数区可见 | 区分光标 1/ΔX 与自动频率测量，单张照片不能证明长期稳定 |

SDG2082X 照片上方只露出另一台万用表的部分接线柱，无法确认其型号，也不能把它视为 SDM3055X-E。万用表模板目前依据老师提供的 SDM3055X-E 手册。

## SDS2202X Plus 可确认的识别提示

屏幕在左，控制区在右。前面板下方有 1 和 2 两个模拟输入接口、DO-D15 数字接口、USB Host 和 Cal 区，以及右侧 WaveGen BNC。控制区可读 Measure、Print、Auto Setup、Run Stop、Cursors、Touch、Default、Clear Sweeps、Setup、Normal、Auto、Single、Level、Vertical、Horizontal、Math、Ref、Acquire、Display、Save Recall、Utility、Digital、AWG、Search、Navigate、History、Decode。

这些是照片可见的文字与位置，未建立对应 Plus 说明书中的功能、后面板或操作流程。它们可以帮助后续补齐 Plus 专用模板，但本次不将该提示自动装载为 HD 模板，也不宣称已经支持该型号的操作指导。
