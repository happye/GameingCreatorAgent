# 连续玩法理解验证与接手

2026-10-04用户否决截图式描述：打Boss、跳跃玩法、射击玩法无可用结果。此为定性验收失败，正式独立U10尚未执行；F006继续false。管线/JSON/索引技术通过不能代替动作理解。

## 修正边界

旧v2已一起发送5帧，但允许单帧事实。v3新增连续动作要求，真实试验被evidence_outside_range拒绝；原响应未保存，具体坏端点未知。当前v4用独立prompt/schema，由模型选起止frame alias、程序生成源时间`[firstUs,lastUs+1)`，免去模型微秒算术。端点须出现在有序引用内，动作至少有两个不同时刻且不同图像hash的证据。旧版本原样保留，新配置创建新run。

v4要求主体→动作变化→可见结果，不把枪、大怪、空中姿态自动视为射击、Boss战、跳跃。多帧合同只是必要条件；模型仍可能给出跨镜头过程、含糊标签或静帧幻觉，不能由有效JSON推断玩法正确。

试验profile为2FPS、9帧、重叠2帧，覆盖首末约4秒；比旧1FPS/5帧增加密度，没有增加时间跨度。跨镜头不能推断连续故事，窗口结果不无条件合并。完整动作片段整合、候选精分析、长Boss遭遇仍需后续验证。

[DeepSeek官方多图合同](https://api-docs.deepseek.com/guides/vision/)允许flash接收9张512宽图，但没有游戏动作准确率承诺；[价目](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)仍匹配2026-10-04快照。官方Pro不支持图片，不能用名称推断能精分析视频。用量/失败/重试按现有账本记录，不降低1M输入保守预留，unknown不当零。

## 接手顺序

1. 读HANDOFF/assignments/worker sprint，核对root与独立worktree提交。只集成独占文件，worker提交不等于root通过。
2. 先测provider：v1/v2仍5图、v3/v4最多9图、时间顺序/单帧/复制图/别名端点/范围/空动作，核对旧prompt hash不变；再测配置、SQLite回读/恢复和完整verify。
3. validate-temporal-gameplay.py不带`--execute`先冻结源hash、采样、prompt/schema及同4秒窗口；付费执行才加`--execute`。默认v4，也可显式`--temporal-prompt phase0-vision-v3`重现旧合同。使用全新ignored目录，禁止覆盖旧实验。
4. A为v2稀疏5帧；B为v4密集9帧；`--same-frame-control`增加v4/C的同5帧，区分prompt/输出合同与采样密度影响。静帧模型应返回空；动作被验证器拒绝只能证明阻止假事件，不能称模型控制通过。倒序源时间本地拒绝不等于反向播放理解。近似负例/强切镜后续另冻样本。
5. 人工看实际区间，区分主体、动作阶段、结果与未见信息。跑Boss/跳跃/射击的lexical/semantic/hybrid，分别诊断上游没产生动作还是检索丢弃，不以降阈值补质量。
6. 小范围改善后再做完整新run/UI复核。正式验收仍按human-acceptance-guide的独立会话/预冻结人工参考进行，开发对照qualityGate=null。

本轮源视频留本地，API仅传选定图片；工具/依赖/缓存在项目内。当前提交和未完成项以sprint-temporal-gameplay为准，未运行的实验不得填写成功。

## 已执行开发证据

| 输出目录（artifacts/下） | 结果 | 已知API估价 |
| --- | --- | --- |
| temporal-v4-execute-0 | 0–4s A/B/C通过，静帧空、倒序发送前拒绝；主要转场 | ¥0.0093252 |
| temporal-v4-execute-28 | 28–32s A/B/C通过，静帧幻觉被拒绝 | ¥0.00974288 |
| temporal-v4-atom-8 | 8–12s B通过但jump/下落歧义，C边界失败，静帧幻觉被拒绝 | ¥0.01037184 |

每次4个HTTP尝试/28输入图、unknown0、qualityGate=null，均非账单。不得只报告成功B而隐去控制/失败费用。

完整Atom run `96b5f01530ce43e2944828fb0520b9b4`：54.743220s、16窗口/40事件/0转录，估价¥0.05029788；可在工作台标记“连续动作（试验）”下回看。v4检索已排除初始jump3里的明确否定事件，现在hybrid2（11.5–12.5s、0–2s）；Boss/射击hybrid0、移动10，pure semantic各10。新报告temporal-retrieval-atom-v4-negation保留全部五查询/三模式。图像联合描述有所变化，但故事/完整动作与独立检索验收仍未通过。
