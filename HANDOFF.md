# HANDOFF（覆盖快照）

## 最近一次会话（2026-11-19）

继续在原分支 `codex/knowledge-version-compare-20261108` 开发，先看 [STATUS](STATUS.md) 和 [看板](docs/progress/index.html)。本批 P041 接通一次提案里的变速和换序。六个 Codex 角色的模型更新与两份 Markdown 路由说明已推送。验证服务 `http://127.0.0.1:8768/studio`，启动信息见 `.cache/workspace/port-8768.json`。

## 实证与接手入口

- 真实项目 `artifacts/demo-phase0`，漫画群星 run `f76f5d6495314c04ae04083614d4afd6`，作品 `55f97422dabd6c5a3d87eb323018e45a`。
- [P035 按内容短版](docs/exec-plans/sprint-platform-content-cut.md)：发布 `5462eed2c820468eb4beb5c1c5ac94d1` 下，抖音「蓝色火焰」选 7.50–22.50 秒，批次 `839555683738ea3b2313e035acae19f6` 重开 2/2，复用全长 B 站。抖音 `96d87ad5860e4732b117fde119a880f1` 的 450 帧、15 秒音画及三帧与源音频对应关系已核对。导出区间随 profile 冻结，旧仅时长配置仍从零开始。内容匹配只采用仍被成片完整保留的证据描述；时长须容纳匹配镜头。浏览器实测未保留证据的关键词被拒绝。产物 `.cache/scratch/platform-content-cut-20261119/`。
- [P041 本地一句话组合](docs/exec-plans/sprint-one-line-mixed-replacement.md)：换镜加删尾可原子撤销、恢复和出包。产物 `.cache/scratch/one-line-mixed-20261119/`。
- 上批合同 [混合剪辑](docs/exec-plans/sprint-mixed-timeline.md)、[平台短版](docs/exec-plans/sprint-platform-short-pack.md)、[画面文案](docs/exec-plans/sprint-platform-video-copy.md) 与 [持久队列](docs/exec-plans/sprint-package-batches.md) 已落地。旧 8766/8767 服务、原片、旧分析、收据和账本保留。
- [P041 AI 组合剪辑](docs/exec-plans/sprint-ai-mixed-timeline.md)：同父版本调用一次（`0881f080…`，估算 ¥0.013006），可按描述选候选，同时处理另一个镜头。取回保存提案并应用为 `69d69600686a4c7a9107600762942905`，试听 27 秒成片 `a23a5d2191734b178920af0c6a627bba`，B 站包 `d49e0570d1d24bf9be6165259e13786d`。产物 `.cache/scratch/ai-mixed-20261119/`。同一准备记录已发送，继续验证从结果入口读取。
- [平台文案起草](docs/exec-plans/sprint-platform-copy-draft.md)和 [多关键词短版](docs/exec-plans/sprint-platform-joined-cut.md)已实测声音与画面逐段对应、队列重开和 B 站包复用。产物 `.cache/scratch/platform-{draft-copy,joined-cut}-20261119/`。
- [AI 组合动作](docs/exec-plans/sprint-ai-combined-actions.md)：已完成真实请求 `638022c8…`（估算 ¥0.013668）。在原 v5 父版删首镜、原第 2 镜后插 5–6 秒「6880」技能、原第 4 镜裁 6–6.5 秒。结果可只读恢复，草稿刷新后保存 `53c8649bd6a7440498fa7b0c21d62e90`，27 秒成片 `16be211485104ed79d82e56920f70245`，B 站包 `bb926109ad804720af2c73c53aa81bb4`。产物 `.cache/scratch/ai-combined-insertion-20261119/`。
- [主题选段](docs/exec-plans/sprint-platform-theme-ranking.md)：发布 `fec2d775c06d438cb2f0d0c259b24a1d` 里按一句主题用本机 E5 排序，试听并选中 2.50–3 与 10–11 秒。批次 `1b4d310e9284df05851544d0aba95c76` 恢复 2/2，B 站复用，抖音 `c6085532b48445c28195ca36185a4585` 有声播放 1.5 秒、下载七文件。实证 `.cache/scratch/platform-theme-cut-20261119/approved-selection/`。
- [组合变速和换序](docs/exec-plans/sprint-ai-combined-speed-order.md)：已完成 v3 请求 `cd011716…`，估算 ¥0.01371。实测删首镜并将原第 4 镜移到第 2 镜前、0.5×播放。保存版 `2f3d49504af649549f79deb87075c85e`，成片 `4913aff4e87b4292968f3694eb6aa6d1`，B 站包 `76e354d57c08489293861041b859bc73`。实证 `.cache/scratch/ai-speed-order-20261119/`。

## 下一优先级与约束

P041 接入同一次提案中的多段插入，需扩展保存与恢复对多插入锚点的支持，维持已有回执版本可读。沿当前分支交付，关键切片更新 Dashboard。原未跟踪方案与工作树保留。先前待推送的两笔提交已于 GitHub 恢复连通后推送。

本批使用单项定向测试、真实浏览器和产物验证，无全量、Release、支付或上传。旧完整 verify-20261117-002506 按用户要求中断，曾见失败。J1 第五次人评未过，J2/J3 待人评，工程实证不改质量和 passes。文字月 ¥30/单条 ¥1、指定视觉月 ¥50，现有费用门禁保留。本机声音，真实平台发布或支付须另授权。
