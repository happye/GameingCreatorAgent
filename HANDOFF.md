# HANDOFF（覆盖快照）

## 最近一次会话（2026-11-20）

继续在原分支 `codex/knowledge-version-compare-20261108` 开发，先看 [STATUS](STATUS.md) 和 [看板](docs/progress/index.html)。本批 P042 接通同平台版本成效对比和下一次结构参考。六个 Codex 角色的模型更新与两份 Markdown 路由说明已推送。验证服务 `http://127.0.0.1:8772/studio`，启动信息见 `.cache/workspace/port-8772.json`。

## 实证与接手入口

- 真实项目 `artifacts/demo-phase0`，漫画群星 run `f76f5d6495314c04ae04083614d4afd6`，作品 `55f97422dabd6c5a3d87eb323018e45a`。
- [P035 平台内容短版](docs/exec-plans/sprint-platform-content-cut.md)、[多关键词拼接](docs/exec-plans/sprint-platform-joined-cut.md)、[画面文案](docs/exec-plans/sprint-platform-copy-draft.md)与[本机主题选段](docs/exec-plans/sprint-platform-theme-ranking.md)均有真实成片与队列实证。旧原片、旧分析、收据和账本保留。
- [P041 本地组合](docs/exec-plans/sprint-one-line-mixed-replacement.md)与[AI 组合动作](docs/exec-plans/sprint-ai-combined-actions.md)已实测换镜、插入及删裁，草稿恢复、试听与出包。
- [组合变速和换序](docs/exec-plans/sprint-ai-combined-speed-order.md)：已完成 v3 请求 `cd011716…`，估算 ¥0.01371。实测删首镜并将原第 4 镜移到第 2 镜前、0.5×播放。保存版 `2f3d49504af649549f79deb87075c85e`，成片 `4913aff4e87b4292968f3694eb6aa6d1`，B 站包 `76e354d57c08489293861041b859bc73`。实证 `.cache/scratch/ai-speed-order-20261119/`。
- [多段插入](docs/exec-plans/sprint-ai-multiple-insertions.md)：已完成 v4 请求 `29dbf347…`，估算 ¥0.013962。原第 2 镜后顺序插两段，原第 4 镜后插第三段，字幕预览及删一段再撤销通过。恢复保存版 `d1b09d174ca04691b2c7607e7c19ca5f`，29.5 秒成片 `87cb80f1236f4d4bb89ee8259c2c3c79`，B 站包 `fbbf0aee6ef441ca9d2e060cc80f22ab`。产物 `.cache/scratch/ai-multi-insert-20261119/`。

- [随原镜移动](docs/exec-plans/sprint-shot-companion-timing.md)：基线 9dd89d1c1682437cbfa61f3ab1fe187e 中旁白与图层均从第 30 帧开始，删首镜后选择随镜则均移动至第 0 帧。恢复保存 b45858e8625448cea4f30b35f56f7b87，成片 e7aa502dfbe7485499413f2bda98c26a，B 站包 cba5bbf0e51d4581ac922fa16e26ca73。实证 .cache/scratch/shot-companions-20261119/，本次零模型调用。

- [AI 随镜时长校验](docs/exec-plans/sprint-ai-companion-fit.md)：基线 d605fd9f17ef4bc7add6aeeb62829286 中两项素材的原时刻分别越界，随镜后旁白第 360 帧开始，图层第 795–825 帧。回读和恢复后保存 6c5680e4cb34459c9aee4af9bea3066e，27.5 秒成片 5ac93d7613884faab6d86f86974aa1a5，B 站包 6655f859c76c4106971a14a359a3b152。一次文字请求，估算 ¥0.01302736，证据 .cache/scratch/ai-companion-fit-20261119/。

- [P042 方案结构偏好](docs/exec-plans/sprint-creator-structure-feedback.md)：独立测试作品 458ed39e51b6f469e90bf8bf78d2e62d。基线 cd1403c3a8464be59cbee6ebcf030218 首推玩法展示，记录偏好刷新后 a06a5e6b997f4a0eac148c526bd711b8 首推倒序，30 秒成片 b0ed34e8925c44d6a83e3b002e38004a，B 站包 918ebaca8e1e4069a7f42b2c61c21157；跨标签清除后恢复默认。产物 .cache/scratch/creator-structure-20261119/，零模型调用。

- [P042 发布成效](docs/exec-plans/sprint-publication-outcome-feedback.md)：在发布 42f0de2b00554505a885b3349961f319 的真实 B 站包 918ebaca8e1e4069a7f42b2c61c21157 浏览器登记 1d350c288d521f620d18f5d0bb719280 和 0e0e3260eda831ce292374dbed6cdb1e 两条测试示例。重开读回、幂等重试与不同包隔离通过。证据 .cache/scratch/publication-feedback-20261120/，零模型调用。

- [P042 成效对比和结构参考](docs/exec-plans/sprint-outcome-structure-reference.md)：隔离库用 B 站真实素材包 918ebaca8e1e4069a7f42b2c61c21157 与 a572a837b3dc4422bda2d4030d3a6c34 对比模拟结果，选择倒序后 1946675176534f6c91de7f83b7fd5496 首推并保留日期与指标。证据 .cache/scratch/outcome-reference-20261120/，原库摘要一致。

## 下一优先级与约束

P042 已接通手录、对比和参考，真人与平台成效待验。接着按路线推进未完成节点，优先 P043 玩法展示。以 J1 第五次试用问题和现有真实录像为依据，补成片结构与镜头选择的交付缺口。真实上传、账号接入及付费行为保留各自授权。

本批使用定向回归、真实浏览器和产物验证，无全量、Release、支付或上传。旧完整 verify-20261117-002506 按用户要求中断，曾见失败。J1 第五次人评未过，J2/J3 待人评，工程实证不改质量和 passes。文字月 ¥30/单条 ¥1、指定视觉月 ¥50，现有费用门禁保留。本机声音，真实平台发布或支付须另授权。
