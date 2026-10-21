# Sprint：TD010 混合语义边界与离线 DB 形对照

**状态（2026-10-22）：代码已落地，待推送。** 否定护栏不再把 `positive_text` 回退到含 mechanicTags 的 `text`；transcript 文档显式写入 `positive_text`；新增混合通道（事实／字幕／裸标签）边界测试与离线 golden JSON 对照。0 付费；不代选 A／B／D；不标 F006 true；不宣称人评／验收通过；不声称覆盖缺口已清；不宣称 TD010 真实 DB run 已关单。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`retrieval.py`、`test_retrieval_negation.py`、`tests/fixtures/td010_mixed_semantics_shapes.json`、本 sprint、tech-debt／交接顶栏
- 不做：付费视觉、改 feature_list 为 true、代选 A／B／D、声称 F006／人评通过、声称真实四 run 对照完成

## 白话

上一轮挡住了「事实说没有跳跃、标签却写 jump」的假命中。这一轮补两块：一是代码不再在空事实时把标签正文塞回否定扫描；二是用「像库里 Completed 时间轴」的离线夹具把混合情况钉住——只否认跳跃仍可被攻击查询命中、字幕里的肯定可以压过事实否认、事实+字幕双否认仍排除、只有标签没有事实时仍可按标签检索。这是离线边界合同，不是真实库对照验收。

## Acceptance

- [x] 事件 `positive_text` 仅 facts／transcripts，禁止 `or text` 回退
- [x] transcript 文档设置 `positive_text`
- [x] 否定扫描只读 `positive_text`
- [x] 混合语义 pytest + golden JSON 对照绿
- [ ] 已推送 `origin/main`（推送后勾）
