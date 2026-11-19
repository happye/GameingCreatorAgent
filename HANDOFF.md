# HANDOFF（覆盖快照）

## 最近一次会话（2026-11-20）

继续在原分支 `codex/knowledge-version-compare-20261108` 开发，先看 [STATUS](STATUS.md) 和 [看板](docs/progress/index.html)。本批接通本机旁白字幕并验证 60 秒成片。六个 Codex 角色的模型更新与两份 Markdown 路由说明已推送。验证服务 `http://127.0.0.1:8772/studio`，启动信息见 `.cache/workspace/port-8772.json`。

## 实证与接手入口

- 真实项目 `artifacts/demo-phase0`，漫画群星 run `f76f5d6495314c04ae04083614d4afd6`，作品 `55f97422dabd6c5a3d87eb323018e45a`。
- [P035 平台内容短版](docs/exec-plans/sprint-platform-content-cut.md)、[多关键词拼接](docs/exec-plans/sprint-platform-joined-cut.md)、[画面文案](docs/exec-plans/sprint-platform-copy-draft.md)与[本机主题选段](docs/exec-plans/sprint-platform-theme-ranking.md)均有真实成片与队列实证。旧原片、旧分析、收据和账本保留。
- [P041 本地组合](docs/exec-plans/sprint-one-line-mixed-replacement.md)与[AI 组合动作](docs/exec-plans/sprint-ai-combined-actions.md)已实测换镜、插入及删裁，草稿恢复、试听与出包。
- [组合变速和换序](docs/exec-plans/sprint-ai-combined-speed-order.md)，实测细节见交付记录。
- [多段插入](docs/exec-plans/sprint-ai-multiple-insertions.md)，实测细节见交付记录。

- [随原镜移动](docs/exec-plans/sprint-shot-companion-timing.md)，实测细节见交付记录。

- [AI 随镜时长校验](docs/exec-plans/sprint-ai-companion-fit.md)：基线 d605fd9f17ef4bc7add6aeeb62829286 中两项素材的原时刻分别越界，随镜后旁白第 360 帧开始，图层第 795–825 帧。回读和恢复后保存 6c5680e4cb34459c9aee4af9bea3066e，27.5 秒成片 5ac93d7613884faab6d86f86974aa1a5，B 站包 6655f859c76c4106971a14a359a3b152。一次文字请求，估算 ¥0.01302736，证据 .cache/scratch/ai-companion-fit-20261119/。

- [P042 方案结构偏好](docs/exec-plans/sprint-creator-structure-feedback.md)：独立测试作品 458ed39e51b6f469e90bf8bf78d2e62d。基线 cd1403c3a8464be59cbee6ebcf030218 首推玩法展示，记录偏好刷新后 a06a5e6b997f4a0eac148c526bd711b8 首推倒序，30 秒成片 b0ed34e8925c44d6a83e3b002e38004a，B 站包 918ebaca8e1e4069a7f42b2c61c21157；跨标签清除后恢复默认。产物 .cache/scratch/creator-structure-20261119/，零模型调用。

- [P042 发布成效](docs/exec-plans/sprint-publication-outcome-feedback.md)：在发布 42f0de2b00554505a885b3349961f319 的真实 B 站包 918ebaca8e1e4069a7f42b2c61c21157 浏览器登记 1d350c288d521f620d18f5d0bb719280 和 0e0e3260eda831ce292374dbed6cdb1e 两条测试示例。重开读回、幂等重试与不同包隔离通过。证据 .cache/scratch/publication-feedback-20261120/，零模型调用。

- [P042 成效对比和结构参考](docs/exec-plans/sprint-outcome-structure-reference.md)：用真实 B 站包和模拟指标演练，下一次方案冻结所选结构及来源，原库保留。
- [P043 玩法主题安排](docs/exec-plans/sprint-showcase-topic-coverage.md)：漫画群星方案 `702be335f834438289915e23ac2acaf5` 保留 1V1、3V3 和技能释放，结算提示缺口。30 秒成片 `4af8a0a0166a43ba97a699e8ce4d3f4d`，B 站包 `fedc05d197f647d594d23b0c455ffe34`。证据 `.cache/scratch/showcase-topic-coverage-20261120/`。
- [P025/P043 主题旁白](docs/exec-plans/sprint-showcase-narration.md)：漫画群星 60 秒方案 `acf92d1296a24efaa7519347ac0fc956`，本机 Huihui 旁白 `79c1aa1976294bd2bdeae93d460faa53`，成片 `a440b9b8995945029fbcbeb41a8c4bf4`，B 站包 `7c04b5bb0b534dfdbd6eea68d84663f1`。证据 `.cache/scratch/showcase-narration-20261120/`。
- [P026/P029 旁白字幕](docs/exec-plans/sprint-narration-captions.md)：四句随音轨后移 2.5 秒，修订 `d4ed99deee984284b7178ee20b240085`，成片 `fed21c0e8c9a48d4a770047fcc41dc21`，烧入字幕的 B 站包 `49799e7b3c8148eeb8b5acfb7337a8ac`。证据 `.cache/scratch/narration-captions-20261120/`。

## 下一优先级与约束

玩法展示已能按主题起草旁白并带字幕出片。下一步用真实录像对照 P044/P045 的规则、选段及作品交付，先闭合活动投稿与攻略的实际使用缺口。P042 真人质量与平台成效待验。

本批使用定向回归、真实浏览器和产物验证，无全量、Release、支付或上传。旧完整 verify-20261117-002506 按用户要求中断，曾见失败。J1 第五次人评未过，J2/J3 待人评，工程实证不改质量和 passes。文字月 ¥30/单条 ¥1、指定视觉月 ¥50，现有费用门禁保留。本机声音，真实平台发布或支付须另授权。
