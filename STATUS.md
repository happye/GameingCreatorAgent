# STATUS（唯一当前状态）

里程碑或会话结束时更新一次。数字以 `python -B scripts/status.py` 为准（从源文件计算），本页只写结论和下一步。

## 目标

本地录像 → 时间线 → 检索 → 成片 → 发布包，做到你亲自试过、觉得能用。工具就绪不等于质量通过。

## 主指标：端到端流程（`docs/exec-plans/journeys.json`）

| 流程 | agent 离线跑通 | 你亲自试过 |
| --- | --- | --- |
| J1 玩法展示：录像 → 约 1 分钟成片 + 发布包 | 是（2026-11-20） | **全流程未通过**（2026-11-11 第五次；第三次仅初稿过得去） |
| J2 一句话找片段：前 10 名可用 ≥70% | 是（工具就绪） | 未做（F006 仍 false） |
| J3 安装便携包并启动工作台 | 是（2026-11-01） | 未做 |

次要计数（功能、技术债、人工待办）以 `python -B scripts/status.py` 的输出为准，本页不手抄。

**汇报规则**：只在主指标变化时汇报，中文不超过 150 字，附一个可以打开的产物。

## 当前交付与下一步（2026-11-20）

1. Grok A01–F16 已集成，定向 99/44/3 通过，TD030 解决。代理预览、空间盘点、OCR、方案对照、逐词字幕和多轨已接入。见 [Grok 集成](docs/exec-plans/sprint-grok-repair-integration.md)。
2. 真实漫画群星已跑通 AI 旁白和文案、本机中文合成、成片及平台包。[持久队列](docs/exec-plans/sprint-package-batches.md)覆盖关页继续完成四个平台、停止后续与服务重启后恢复。
3. 抖音短版已接入关键词、多段拼接、画面文案和本机主题选段。实测出片、试听、队列恢复与 B 站全长包复用。见[交付记录](docs/exec-plans/sprint-platform-theme-ranking.md)。
4. 创作助手已实测换镜、删裁、变速、换序及[多段插入](docs/exec-plans/sprint-ai-multiple-insertions.md)。[AI 随镜时长校验](docs/exec-plans/sprint-ai-companion-fit.md)实测先迁移旁白和图层，恢复保存、播放 27.5 秒成片并出 B 站包。
5. [P042 方案结构偏好](docs/exec-plans/sprint-creator-structure-feedback.md)接入工作台。漫画群星刷新后从玩法展示首推改为倒序首推，实测 30 秒成片和 B 站包。另一标签页清除后，生成恢复默认首推。
6. P042 已接通发布成效登记、同平台对比与下一份方案参考，用隔离示例和实拍素材包验证。真实平台数据待录入。见[交付记录](docs/exec-plans/sprint-outcome-structure-reference.md)。
7. 漫画群星 60 秒[主题旁白](docs/exec-plans/sprint-showcase-narration.md)已补齐[句级字幕](docs/exec-plans/sprint-narration-captions.md)，试听、移动音轨、SRT 和 B 站烧入版实测通过。
8. P020/P044 已把示例活动规则接到竖屏成片、发布核对和抖音包。见[活动投稿](docs/exec-plans/sprint-campaign-submission.md)。
9. [P045 攻略](docs/exec-plans/sprint-guide-evidence.md)和[P046 解说](docs/exec-plans/sprint-commentary-evidence.md)已实测画面引用、配音和出包。
10. [P047 实况](docs/exec-plans/sprint-live-cut-continuity.md)用《代号 Atom》验证连续取材、原声和出包。下一步推进 P048 高光。

## 费用与授权

- 2026-11-08：用户要求尽量避免PR/AE等大型软件。开发、日常验证和成片导出走项目FFmpeg/浏览器路径，专业格式为可选交接，实际导入保持未验。此前Premiere退出由用户手动关闭，不是软件故障；不转成人工待办。

- 2026-11-09：用户先后授权2次动态策划调用，均已耗用：①估算¥0.0094516（7abf86df…，failed:validate_proposal，原输出留存）②估算¥0.0174276（成功并采用）。不得重发；之后的调用按2026-11-11月度预算规则。
- 2026-11-05：用户要求语音暂用免费本机声音；不自动切换云端。
- 2026-11-11：创作环节AI文字调用每月¥30、单条视频¥1内自动调用，超出再逐次确认（application/ai_budget.py）。

- 每月预授权 ¥50，只用于你指定的素材；超出每次单独询问；硬发送门禁保留；未知费用不写成 0。
- P038、P046–P051 已于 2026-11-03 由你确认解冻（J1 第三次试看“初版过得去”）。真实平台发布、支付和付费调用仍各自需要你明确授权。

## 测试与提交

- 2026-11-17起按真实素材流程交付，只在实际阻碍处做必要的小范围核对；不主动全量测试。完整或Release检查须用户明确要求。
- 一次提交对应一个能力或一个修复；推送放在里程碑结束、会话结束或长任务开始前。

## 保护（不可撤）

不提交密钥、媒体、数据库；付费有门禁；证据和账本不可改；实现、质量、商业三种状态分开记录；不自动重付、重标；工具链检查可以收窄范围，但不能拆除。

## 文档位置

当前状态看本页；接手看 `HANDOFF.md`；规则看 `AGENTS.md`；历史在 `docs/archive/`、`progress.md` 和 git 记录里。
