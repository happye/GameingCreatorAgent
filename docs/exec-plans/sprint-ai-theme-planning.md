# AI 主题选片与编排说明

P019 / P021 / R3 · 2026-11-12 · active

目标：用户的必须主题进入 AI 选片判断，每个镜头展示为什么能讲该主题及其引用的原始摘要；采用后仍可核对主题覆盖与缺口，不将 AI 建议当作人评通过。

## 范围与合同

- 新准备的有主题 AI 规划使用版本化的主题映射快照与 plan-proposal-v3；无主题和旧准备记录继续 v1/v2 原路径，旧请求哈希、快照和已付费结果可读且可采用。
- 每个 v3 shot 除 candidateId/role 外有 topicUses 列表（可为空），每项严格为 topic、rationale、observationQuote。topic 必须属于 brief，条数/文字有界，同镜头不重复主题；引文必须是该候选 facts 或 tags 中某项的非空原文片段。引文证明引用来源，不证明语义正确。
- 后端编译时仅保留实际进入成片的镜头的映射，并按最终镜头生成 topicCoverage（ai-suggested/missing），缺口不置灰，不修改原片、源区间、证据身份或费用规则。
- 工作台方案检查器显示每个主题对应镜头、理由及摘要引文，并明确需要预览核对。旧方案不出现空主题面板。
- 不增加付费请求，不重发旧请求；本轮用模拟Transport验证。
- 新 v3 输出上限为8192 tokens，容纳多套方案的理由和引文；旧v1/v2保持2048。报价、预算ceiling、费用预留与发送均用记录中的同一上限，原月¥30/视频¥1及锁内复核不变。

## 所有权与验证

- task_developer（Sol/medium）独立 worktree：application/plan_topics.py、plan_proposals.py、tests/test_plan_topics.py；不得修改其他文件。
- 主代理：plan_reasoning.py、provider支持版本、service快照重建、工作台展示、集成测试、文档及Dashboard。
- 唯一关键边界评估：task_quality_guard（Sol/high），覆盖候选/证据/旧版本回放及预算未变；不另派普通审查。
- 验证：新schema/伪造引文/未知主题/旧版本身份、实际剪掉镜头不虚报覆盖、带知识与篮子范围兼容、真实HTTP模拟AI准备→采用→读回，浏览器展示。先定向检查，实质批次结束仅一次完整verify。

## 结果

实现已集成；最终门禁待运行。关键边界静态审查无阻断问题。定向费用/服务/主题回归50过，包含按8192 ceiling锁内拒绝临近月/视频上限。受影响18文件226过；最终浏览器文件17过，含v3知识+片段篮裁剪+主题映射的HTTP准备→采用→刷新读回，以及auto执行HTTP400仍可恢复。旧有主题v1/v2请求hash、结果复用和采用已过。初始范围fixture缺clip_ranges参数及Playwright线程中asyncio.run误用已修测试。J1人评状态不变。
