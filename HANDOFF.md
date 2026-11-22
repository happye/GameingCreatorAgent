# HANDOFF（覆盖快照）

## 最近一次会话（2026-11-22）

当前分支 `main`。先看 [STATUS](STATUS.md) 与 [看板](docs/progress/index.html)。[P035 平台文案](docs/exec-plans/sprint-studio-multi-platform-packages.md)实测关页后出包与重开下载。[P029](docs/exec-plans/sprint-creation-subtitles.md)和[P031](docs/exec-plans/sprint-publication-assets.md)有实拍产物。

[P051 项目品牌资源](docs/exec-plans/sprint-enterprise-basics.md)已实测文案、视觉模板和项目配乐库。配乐移出后，Atom 旧修订重开仍输出原音轨，抖音包 `a3104f45bc9f4410a1e9e4634aff4d6d`。

[P050 本机额度](docs/exec-plans/sprint-creator-plans.md)实测拦截。[P033 专业交接](docs/exec-plans/sprint-premiere-narration-track.md)已实测字幕、透明图层和同版成片混音。

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
- [P043 玩法主题安排](docs/exec-plans/sprint-showcase-topic-coverage.md)，实测保留 1V1、3V3 和技能释放，结算提示缺口。
- [P025/P043 主题旁白](docs/exec-plans/sprint-showcase-narration.md)，60 秒样片完成本机旁白及 B 站打包。
- [P026/P029 旁白字幕](docs/exec-plans/sprint-narration-captions.md)：四句随音轨后移 2.5 秒，修订 `d4ed99deee984284b7178ee20b240085`，成片 `fed21c0e8c9a48d4a770047fcc41dc21`，烧入字幕的 B 站包 `49799e7b3c8148eeb8b5acfb7337a8ac`。证据 `.cache/scratch/narration-captions-20261120/`。
- [P020/P044 活动投稿](docs/exec-plans/sprint-campaign-submission.md)，示例规则和真实漫画群星录像跑通 720×1280 竖屏及标签核对，成片 `95239febcbe04c4da5ee3bf318d986da`，抖音包 `1d9943bc30e040e39368e9aa65360d61`。证据 `.cache/scratch/campaign-submission-20261120/`。

## 下一优先级与约束

Studio 已实拍检索回看入篮及本机导入。下一步把待分析任务接到现有 `analyze --resume` 授权流程，沿用真实运行 ID 和发送门禁。J2 十槽与 J3 独立 Windows 人评待做。

本批使用定向回归、真实浏览器和产物验证，无全量、Release、支付或上传。旧完整 verify-20261117-002506 按用户要求中断，曾见失败。J2/J3 待人评，J1 通过以第六次用户答复为证。文字月 ¥30/单条 ¥1、指定视觉月 ¥50，现有费用门禁保留。本机声音，真实平台发布或支付须另授权。
