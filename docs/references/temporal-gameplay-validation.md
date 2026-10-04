# 连续玩法理解验证与接手

2026-10-04用户否决截图式描述：打Boss、跳跃玩法、射击玩法无可用结果。此为定性验收失败，正式独立U10尚未执行；F006继续false。管线/JSON/索引技术通过不能代替动作理解。

## 修正边界

旧v2已一起发送5帧，但允许单帧事实。新v3任务按源时间联合解释主体、动作变化及可见结果，不把枪、大怪、空中姿态自动视为射击、Boss战、跳跃。动作须引用至少两个不同时刻且不同内容的证据；这只是必要条件，不能证明模型判断正确。旧版本原样保留，新prompt/采样创建新run。

试验profile为2FPS、9帧、重叠2帧，覆盖首末约4秒；比旧1FPS/5帧增加密度，没有增加时间跨度。跨镜头不能推断连续故事，窗口结果不无条件合并。完整动作片段整合、候选精分析、长Boss遭遇仍需后续验证。

[DeepSeek官方多图合同](https://api-docs.deepseek.com/guides/vision/)允许flash接收9张512宽图，但没有游戏动作准确率承诺；[价目](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)仍匹配2026-10-04快照。官方Pro不支持图片，不能用名称推断能精分析视频。用量/失败/重试按现有账本记录，不降低1M输入保守预留，unknown不当零。

## 接手顺序

1. 读HANDOFF/assignments/两个worker sprint，核对root与独立worktree提交。只集成独占文件，worker提交不等于root通过。
2. 先测provider：v1/v2仍5图、v3最多9图、时间顺序/单帧/复制图/范围/空动作，核对旧prompt hash不变；再测配置、SQLite回读/恢复和完整verify。
3. 集成validate-temporal-gameplay.py后先不带`--execute`冻结源hash、采样及同4秒A/B窗口；付费执行才加`--execute`，输出到新的ignored artifacts目录，禁止覆盖旧实验。
4. A为v2稀疏5帧；B为v3密集9帧。静帧控制不得确认连续动作。倒序源时间应本地拒绝；这项输入校验不等于测试真实反向播放理解。近似负例/强切镜/混合PV后续另冻样本。
5. 人工看实际区间，区分主体、动作阶段、结果与未见信息。跑Boss/跳跃/射击的lexical/semantic/hybrid，分别诊断上游没产生动作还是检索丢弃，不以降阈值补质量。
6. 小范围改善后再做完整新run/UI复核。正式验收仍按human-acceptance-guide的独立会话/预冻结人工参考进行，开发对照qualityGate=null。

本轮源视频留本地，API仅传选定图片；工具/依赖/缓存在项目内。当前提交和未完成项以sprint-temporal-gameplay为准，未运行的实验不得填写成功。
