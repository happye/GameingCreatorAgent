# 同候选对照的本地人工记录

2026-10-06，接5bc7029和1683/1skip完整验证。上一Goal turn为实际进展：交付同源对照页、真实双尺寸/下载验证、完整验证与远端核对。按总方案继续Phase 0质量验证准备，不新增模型调用或扩大验收。

## 使用效果与边界

用户可在本地记录页分别填写物品误认、切镜真实性、原正确描述保留、查询片段可用性，下载并重新载入记录。保存入口重验当前来源及每组精确请求/结果/注册帧，拒绝混用其他结果；无真实新版结果时判断、目标实体和说明均保持空值。旧描述意见不扩大为新版或Top-10标签。

日期/填写人可记录；填写任何判断须同时给出日期、填写人和说明，未判断保持null。true/false的含义按问题单独解释，不合成一个模糊通过分数。实体仅引用当前v4 scene的entityId，不借用旧shot/actor ID。输出是新的本地记录包，不覆盖原报告、反馈、画面、侧车或账本。

## 归属与计划

root在codex/visual-details顺序开发；独占新application/detail_pilot_review.py、infrastructure/detail_pilot_review_files.py、tests/test_detail_pilot_review.py，并修改自己已集成的scripts/prepare-detail-pilot-comparison.py及其测试。已有worker及worktrees冻结，不发起并行writer。

1. 纯Application严格解码并绑定原模板来源，保留四个判断维度及空值，支持完整原记录的再次编码。
2. 本地记录页填写／载入／下载；使用显式本地文件，不访问网络，原图与描述可对照，新版缺结果禁填。
3. 现有只读生成器增加显式记录页输出与record验证/保存模式；每次重跑原来源核对，不仅信任外来JSON自报hash。输出新目录独占文件，原记录不覆盖。
4. 覆盖换case/request/payload/frame/源hash、bool冒充整数、重复键、非法日期/实体、缺结果打分、空值及跨字段伪造；真实原六帧和1366/390操作回放、源快照不变；最终一次完整verify。

恢复：开始时root工作树5bc7029干净，scaffold检查通过；本切片尚无实现或新验证。先完成纯合同再接记录页，未通过源码仅保存检查点，不替代旧1683。新v4授权待答、0新请求/预留，旧unknown¥4.065536和F006/F009/F010保持。
