# STATUS（唯一当前状态）

里程碑或会话结束时更新。计数用 `python -B scripts/status.py`。

## 目标

本地录像 → 时间线 → 检索 → 成片 → 发布包，做到你亲自试过、觉得能用。工具就绪不等于质量通过。

## 主指标：端到端流程（`docs/exec-plans/journeys.json`）

| 流程 | agent 离线跑通 | 你亲自试过 |
| --- | --- | --- |
| J1 玩法展示：录像 → 约 1 分钟成片 + 发布包 | 是（2026-11-20） | **通过**（第六次，用户确认样片可发；平台包下载故障单独跟踪） |
| J2 一句话找片段：前 10 名可用 ≥70% | 是（Studio 已实拍回看、入篮） | 未做（F006 仍 false） |
| J3 安装便携包并启动工作台 | 是（2026-11-22，开发机实拍导入） | 未做 |

**汇报规则**：只在主指标变化时汇报，中文不超过 150 字，附一个可以打开的产物。

## 当前交付与下一步（2026-11-23）

Studio 已交付镜头、画面文字定位和单条代理回收。下一步核对 P008 缓存缺口。J2 十槽评分与 J3 独立 Windows 验收留到测试阶段。

1. [P035 平台文案](docs/exec-plans/sprint-studio-multi-platform-packages.md)实测 Atom 同稿各自出包。[P029](docs/exec-plans/sprint-creation-subtitles.md)实测青色宋体。
2. 真实漫画群星已跑通 AI 旁白和文案、本机中文合成、成片及平台包。[持久队列](docs/exec-plans/sprint-package-batches.md)覆盖关页继续完成四个平台、停止后续与服务重启后恢复。
3. [抖音短版](docs/exec-plans/sprint-platform-theme-ranking.md)支持关键词、拼接、画面文案和本机主题选段，实测出片、队列恢复与 B 站全长包复用。
4. 创作助手已实测换镜、删裁、变速、换序和[多段插入](docs/exec-plans/sprint-ai-multiple-insertions.md)。[旁白和图层随镜迁移](docs/exec-plans/sprint-ai-companion-fit.md)实测重开、成片和 B 站包。
5. [P042 方案结构偏好](docs/exec-plans/sprint-creator-structure-feedback.md)实测漫画群星改用倒序首推、导出成片及 B 站包。跨标签清除后恢复默认排序。
6. [P042 发布成效](docs/exec-plans/sprint-outcome-structure-reference.md)支持登记、同平台对比和下一次策划参考。实拍素材包与示例指标已验证，真实数据待录入。
7. 漫画群星 60 秒[主题旁白](docs/exec-plans/sprint-showcase-narration.md)已补齐[句级字幕](docs/exec-plans/sprint-narration-captions.md)，试听、移动音轨、SRT 和 B 站烧入版实测通过。
8. P020/P044 已把示例活动规则接到竖屏成片、发布核对和抖音包。见[活动投稿](docs/exec-plans/sprint-campaign-submission.md)。
9. [P045 攻略](docs/exec-plans/sprint-guide-evidence.md)和[P046 解说](docs/exec-plans/sprint-commentary-evidence.md)已实测画面引用、配音和出包。
10. [J1 命名出包](docs/exec-plans/sprint-j1-trial-reopen.md)已实测保存到项目 `exports`。
11. [配乐](docs/exec-plans/sprint-mode-music-recommendations.md)与[品牌资源](docs/exec-plans/sprint-enterprise-basics.md)已实拍出包。
12. [分析额度](docs/exec-plans/sprint-creator-plans.md)实测拦截。[专业时间线](docs/exec-plans/sprint-premiere-narration-track.md)实测字幕、图层和混音。

## 费用与授权

- 2026-11-08：用户要求尽量避免 PR/AE。成片和日常验证走 FFmpeg 与浏览器。专业格式为可选交接，剪辑软件实导待验。

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
