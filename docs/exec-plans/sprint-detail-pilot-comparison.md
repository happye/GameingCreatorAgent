# 同候选旧版与连续实体版的人工对照

2026-10-06，接描述反馈1661/1skip完整验证与生产读取检查点a424ef4。依原总方案先验证画面理解与检索可用性，保持Phase 0范围。真实v4两次/最高¥4.07/原六图发送授权仍待答，这个切片仅离线读取与生成本地页面。

## 用户效果

把35–36秒保留正例、28–29秒抵镜头物品反例的原三个画面、旧模型描述、已有人工纠错和新版结果放在同一页。用户可以在相同画面下比较，不必来回切版本。新版精确key缺结果时标“未执行/暂无结果”，不编造结果，也不把旧确认贴到新版。

人工记录分别询问物品误认、切镜真实性、正例描述保留和所查片段可用性，默认null。描述级反馈与独立检索人评分开，两个候选不能替代Top-10十固定槽、≥7独立有用事件的门槛。

## 分工与边界

- detail_parts_v3：新独立`.worktrees/detail-pilot-compare` / `codex/detail-pilot-compare`，基线a424ef4；只写新scripts/prepare-detail-pilot-comparison.py、tests/test_detail_pilot_comparison.py和own sprint。旧proposal/parts/temporal worktrees冻结，不改Provider、账本、公共文档或源数据。
- root：审核接口，真实本地生成与桌面/手机核对、共享文档及集成。其余worker冻结；detail_workspace_review只读提出此下一切片，无代码写入。

调用者必须提供已冻结proposal的预期SHA `06829ab9dc835545ef8c4de5c829351fc686ce70c990d8c902b9b919b2f062c6`，原路径artifacts/detail-temporal-validation/pilot-proposal.json。核对case/run/event/canonical request/requestHash/注册帧源时刻与hash，以及legacyRequestHash与原report/feedback的payload。原报告通过现有description report validator；当前新v4侧车沿用完整reuse_or_refuse和scene投影核验，不能扫描mtime或借别版。

仅输出独立ignored artifacts/detail-pilot-comparison的新HTML/JSON/人工记录模板，普通文字安全显示；不覆盖旧报告、模型结果、人工反馈、冻结请求或源帧。无Provider调用、预算预留、恢复、重试或SQL写入；旧未知¥4.065536保留。

## 验证与恢复

2026-10-06用户最新额度提示15%，要求准备阶段汇报，未要求停工。root已核对工作树0a97abb干净、冻结proposal SHA不变、0新paidRequests、executionAuthorized=false、原report SHA不变和生产35992健康；上一goal turn为已验证功能交付的实际进展。当前worker接口已定，尚无可用生成结果/新验证，不能写成页面已完成；阶段报告report-2026-10-06-stage-progress.md按此事实保存。下一节点等worker提交其独占文件后审核/定向/实际生成，不复制未验收口头结果为通过。

必要反例：错误proposal SHA/case/run/request/帧ID源时间hash拒绝；v4缺结果保持未执行；旧反馈仅贴原结果；HTML文字安全；输出不覆盖来源；人工字段默认null；真实源表/侧车/账本/反馈/proposal前后不变。生成页面在1366桌面/390手机核对原六图和布局。相同query的新匹配只有新结果存在时计算，不能用模型工程fixture替代真实效果。

已有工作台实现未改，本切片完整验证仍以1661/1skip检查点为基线；新增生成器先做针对其来源绑定与只读行为的检查。进展与下一动作随节点追加，当前worker在实现独占三个文件。新v4授权继续待答，不能因旧预算有余额再调用。
