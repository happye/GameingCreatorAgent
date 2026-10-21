# Sprint：TD010 本机 Completed 只读对照（artifacts DB）

**状态（2026-10-22）：代码已落地，待推送。** 对 `artifacts/demo-phase0` 的 Completed run 与 `artifacts/independent-footage-20261011` 的 coverage-gap run 做 SqliteTimelineStore `read_only` 冒烟：positive_text 不含裸 mechanicTags 回声、否定护栏不泄漏进 lexical hits、tag-only「攻击」仍可检索、coverage-gap 拒绝可检索加载。验证方式=**pytest + 本机只读 DB**；无 DeepSeek／launcher／付费／浏览器。不代选 A／B／D；不标 F006 true；不宣称人评／验收通过；不声称覆盖缺口已清；不宣称 TD010 全库／四 run 关单。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`main`
- Owned：`tests/test_retrieval_local_completed_td010.py`、本 sprint、tech-debt／交接顶栏
- 不做：付费视觉、改 feature_list、代选 A／B／D、声称 F006／人评通过、改写 artifacts 库

## 白话

仓库里已经有本机 Completed 时间轴（demo-phase0）和带覆盖缺口的长片库。这一轮不新开分析、不花钱，只只读打开库跑检索护栏：标签不能污染否定扫描用的正文；有缺口的 run 不能当可检索验收数据。缺 artifacts 时测试 skip，不假绿。

## Acceptance

- [x] demo-phase0 Completed run 只读加载 + positive_text 标签纯度
- [x] 否定集合与 lexical hits 不相交
- [x] tag-only「攻击」仍可 lexical 命中且 positive_text 无「攻击」
- [x] independent-footage coverage-gap → `retrieval.coverage_gap`
- [ ] 已推送 `origin/main`（推送后勾）
