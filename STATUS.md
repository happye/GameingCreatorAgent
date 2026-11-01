# STATUS（当前唯一状态源）

> 里程碑或会话结束时更新本文件一次。**仅当下方「主指标」数字变化时**向用户汇报；勿为记下 tip SHA／推送结果再开文档提交。

## 目标
离线优先把「录像→时间线→检索→创作成片／发布包」做到可验收；不把工具就绪当成质量通过。

## 完成标准（未宣称已达成）
- 首产品路径（玩法展示／活动投稿／攻略）有真人质量验收证据（F006 等仍 false）
- 付费视觉／发布／支付仅在明确授权下发生；证据与 ledger 不可篡改
- 离线主路径冒烟（无付费）：见下方「离线命令」；完整 `./scripts/verify.ps1` 非每会话必跑

## 主指标（e2e primary — 汇报门槛）
口径：看板 + `feature_list.json`；分层 ✅交付／🟡部分／⬜未开始；质量／发布口径分离。会话打印：`python -B scripts/status.py`。

| # | 指标 | 当前值 |
| --- | --- | --- |
| 1 | 计划功能 51 | 已交付 10 · 部分 41 · 未开始 0（约 60%） |
| 2 | 首产品 ★22 | 已交付 0 · 部分 22 · 未开始 0（约 50%） |
| 3 | Phase0 F000–F010 | passes true 8 · false 3（**F006/F009/F010=false**） |
| 4 | 质量验收真步骤 | **0/8**（看板 §3；工具就绪≠人评完成） |
| 5 | 技术债 | 21 项：已解决 14 · 部分 2 · 未解决 5 |
| 6 | 人工 | 必做 0 · 未来见 human-inputs（看板摘要与表可能差 1，以表为准核对） |

**汇报格式**：≤150 字中文 + **一个**可打开产物路径；仅当上表数字相对上次汇报有变。

## 下一步
1. 人评／体验（触发时登 human-inputs；不催）
2. 离线债：TD009／TD004／TD002（按当次指令）
3. 安装包／签名／许可证（分发前）
4. **冻结至首个模式完成人评前**：P046–P051、P038（不新开、不扩 scope）

## 费用预授权
- 月度预授权 **¥50**：仅**用户指定素材**的分析类调用
- 超出须**每次再问**；**硬发送门禁**保留（无门禁不得真发送）
- 零扣费人工确认见 `docs/references/detail-billing-confirmation-guide.md`（不授予新调用）
- 不重付、不重标；未知费用不得写成 0

## 功能冻结
首个内容模式（玩法展示／活动投稿／攻略）完成人评前：**冻结 P046–P051 与 P038（自动发布）**。`feature_list.json` 状态勿因 harness 改动翻转。其余 partial 可按指令小修。

## 离线命令（主路径，无付费）
```
python -B scripts/status.py
python -B scripts/validate-demo.py --project artifacts/demo-phase0 --run f76f5d6495314c04ae04083614d4afd6
python -B scripts/validate-inspection-ui.py --project artifacts/demo-phase0 --run f76f5d6495314c04ae04083614d4afd6
```
长门禁：`./scripts/verify.ps1`（format/lint/types/pytest/wheels）— 非每会话必跑。

## 保护（不可撤）
不提交密钥／媒体／数据库；付费有门禁；证据与 ledger 不可变；实现／质量／商业口径分离；不自动重付／重标；工具链检查可收窄不可拆除；.cache 可重建，模型／付费证据／用户创作勿删。

## Tip
见 `git log -1 --oneline`（本文不自写 SHA）。

## 文档习惯
当前=本文件（≤5KB）；接手=HANDOFF.md（≤5KB）；规则=AGENTS.md（≤6KB）；历史=`docs/archive/`／progress.md／git；看板数字有变再改 progress-board.md。
