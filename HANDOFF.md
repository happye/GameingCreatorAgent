# HANDOFF（覆盖快照）

## 最近一次会话（2026-11-19）

继续在原分支 `codex/knowledge-version-compare-20261108` 开发，先看 [STATUS](STATUS.md) 和 [看板](docs/progress/index.html)。本批补齐 P035 按关键词选连续平台短版、P041 本地和 AI 两种一句话混合剪辑。六个 Codex 角色的模型更新与两份 Markdown 路由说明一并入库。运行验证服务 `http://127.0.0.1:8768/studio`，启动身份与日志见 `.cache/workspace/port-8768.json`。

## 实证与接手入口

- 真实项目 `artifacts/demo-phase0`，漫画群星 run `f76f5d6495314c04ae04083614d4afd6`，作品 `55f97422dabd6c5a3d87eb323018e45a`。
- [P035 按内容短版](docs/exec-plans/sprint-platform-content-cut.md)：发布 `5462eed2c820468eb4beb5c1c5ac94d1` 下，抖音「蓝色火焰」选 7.50–22.50 秒，批次 `839555683738ea3b2313e035acae19f6` 重开 2/2，复用全长 B 站。抖音 `96d87ad5860e4732b117fde119a880f1` 的 450 帧、15 秒音画及三帧与源音频对应关系已核对。导出区间随 profile 冻结，旧仅时长配置仍从零开始。内容匹配只采用仍被成片完整保留的证据描述；时长须容纳匹配镜头。浏览器实测未保留证据的关键词被拒绝。产物 `.cache/scratch/platform-content-cut-20261119/`。
- [P041 本地一句话组合](docs/exec-plans/sprint-one-line-mixed-replacement.md)：父 `6f57066755a04d47b05bbd28b1eb2667` 第 5 镜换候选 1 并删末镜。预览复用草稿后端原子校验，应用后撤销/重做，关页恢复，保存 `5954788195fc482390e87f2a267bf579`。打开该版本导出 `57b8803af3e74fbca403c144378f83f5`，27 秒试听和 B 站七文件包 `87cc1e540f30469991384cab1d430720` 下载通过。使用保存的插入建议复现并验证换镜后删未保存插入段；无付费重发。产物 `.cache/scratch/one-line-mixed-20261119/`，以 verified- 开头的是核对过新版本身份的成片和发布包。首次错选旧父版本的结果仍在，未计入。
- 上批合同 [混合剪辑](docs/exec-plans/sprint-mixed-timeline.md)、[平台短版](docs/exec-plans/sprint-platform-short-pack.md)、[画面文案](docs/exec-plans/sprint-platform-video-copy.md) 与 [持久队列](docs/exec-plans/sprint-package-batches.md) 已落地。旧 8766/8767 服务、原片、旧分析、收据和账本保留。
- [P041 AI 组合剪辑](docs/exec-plans/sprint-ai-mixed-timeline.md)：同父版本调用一次（`0881f080…`，估算 ¥0.013006），可按描述选候选，同时处理另一个镜头。取回保存提案并应用为 `69d69600686a4c7a9107600762942905`，试听 27 秒成片 `a23a5d2191734b178920af0c6a627bba`，B 站包 `d49e0570d1d24bf9be6165259e13786d`。产物 `.cache/scratch/ai-mixed-20261119/`。同一准备记录已发送，继续验证从结果入口读取。

## 下一优先级与约束

P035 下一步按已选平台和内容起草可编辑的画面文案，接入试听和出包，再推进跨镜头选段。P041 继续扩展动作种类和顺序。沿当前分支交付，关键切片更新 Dashboard。原未跟踪方案与工作树保留。

本批使用单项定向测试、真实浏览器和产物验证，无全量、Release、支付或上传。旧完整 verify-20261117-002506 按用户要求中断，曾见失败。J1 第五次人评未过，J2/J3 待人评，工程实证不改质量和 passes。文字月 ¥30/单条 ¥1、指定视觉月 ¥50，现有费用门禁保留。本机声音，真实平台发布或支付须另授权。
