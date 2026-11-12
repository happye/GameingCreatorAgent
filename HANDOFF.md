# HANDOFF（覆盖快照）

## 最近一次会话（2026-11-13，Codex，自主goal仍active）

用户要求按计划持续开发直到额度用光；有额外授权或无法安全解决的阻塞才汇报。不要把单批交付当成整个goal完成。已接手Claude版本；J1第五次未通过，第六次复测待用户方便时进行，不阻断开发。

## 本批主题编排已交付

- 056b252（已推当前分支）：有主题新规划使用plan-proposal-v3，逐镜topicUses严格绑定brief主题、理由和该候选原facts/tags引文；topicCoverage仅计实际编译镜头，缺口不置灰。预览/采用后显示原方案主题安排，手工改镜头需重新核对。引文只证明来源，不冒称语义验证。
- v3输出上限8192，报价/预算ceiling/预留/发送均绑定record.maxOutputTokens；v1/v2保留2048。旧有主题prepared按冻结快照重建，不自动升版本，hash/结果复用/采用兼容。
- 自动策划HTTP400也保留发送身份和只读恢复，不再误称未发送。无真实模型调用或费用；仅模拟Transport。
- 正式quiet.ps1 verify在056b252通过：5226 passed、7 skipped、0 failed，2132秒；格式/Ruff/mypy/CLI通过，未Release。日志.cache/test-logs/verify-20261112-235522.log；verify-last.json=passed。不要再次全量跑此批。
- 受影响18文件226过；浏览器文件17过（知识+裁剪+主题映射HTTP准备/采用/刷新）；门禁后追加EDL渲染合同断言，定向5过，只有测试变更。合同docs/exec-plans/sprint-ai-theme-planning.md与Dashboard已同步。J1人评状态不变。

## 已并行准备下一片，尚未集成/运行测试

独立树.worktrees/work-budget-identity，分支codex/work-budget-identity-20261113，base056b252。勿删除此活动树。

- 合同在该树docs/exec-plans/sprint-work-budget-identity.md，架构师与质量守卫已核设计。目标显式新建作品、稳定workId贯穿brief/多次根plan/AI采用/修订/render，共享月¥30、同作品跨月¥1；解决TD029的历史累计¥1后永久降规则问题。完整多轨工程另片。
- task_developer已停笔，10个归属源码/测试文件：新增infrastructure/creation_work_store.py、ui/creation_works_http.py、ui/creation_budget_scope.py及3份测试；修改application/ai_budget.py、ui/creation_jobs.py、creation_reasoning_service.py、creation_reasoning_http.py。Ruff/mypy静态过，尚未跑pytest，不能称产品交付。没有路由/前端接线。
- 关键审查P1已按建议修：不仅work根，新prepare的可信legacy根也冻结budgetKey；旧prepared不改字节，历史无key用严格解析，坏链归全局?，不再吞错退回中间job重获额度。theme_guard正在增量复查修复，需取最终结论。
- 下一安全动作：主树当前批记录提交推送后，在下一树定向跑3个新测试文件及相关旧reasoning/job测试（先load主树env，借主树venv，cwd仍该worktree；不重新uv sync/安装）。主树verify已终止，可启动一个pytest。修失败后补server作品GET/POST路由、前端显式新建/恢复作品与按作品隔离草稿/最近job/待恢复brief，再做全链采用/导出/费用并发验证和唯一关键评估；不能只交store。

## 保护与授权

当前主分支codex/knowledge-version-compare-20261108已推功能，未合main。原未跟踪设计稿/审计/Grok工单不动；四个旧worktree及stash不动。本批theme-topic-binding树已对照集成字节后移除；下一预算树保留。原片/标签/账本/证据不改，不发布/支付/云配音。文字AI月¥30/视频¥1内，超出再确认；视觉仅指定素材¥50/月，未知成本不写0，失败不自动重付。预算新片未交付前TD029保守限制继续。推送git -c http.proxy=http://127.0.0.1:7890 push。
