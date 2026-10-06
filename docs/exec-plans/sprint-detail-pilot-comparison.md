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

### 最新检查点：真实对照页已可用，全项目检查待运行

worker b58159d已串行整合为4e2829a，其原worktree冻结。root完成中文条件标签和同部件规则说明、查询/实体标签映射隔离，以及直接打开file://时的静态JSON下载修复。新增真实浏览器下载回归，两份下载均与落盘文件逐字节一致；最新定向116 passed（生成器22、proposal18、原报告验证76），生成脚本Ruff和strict mypy通过。1661/1skip仍是之前描述反馈切片的完整基线，本次全项目检查尚未运行。

最终真实产物位于ignored `artifacts/detail-pilot-comparison-20261006-final/`，保留先前产物而不覆盖。1366/390页面均实读六张原图、原尺寸和逐字节hash；三个确认、一个判错只贴旧结果，新版两个候选均no_saved_result；人工维度保持null，模板实际点击下载与落盘一致，无页面错误、外部请求和横向溢出。原报告、反馈、冻结proposal、源DB/侧车/账本前后不变，0Provider/预留变更；独立来源审计与旧partial重算亦通过。

HTML SHA4323e6e8b2f1b2f8a5792f613487dade9f6514ffd9f806f0116a63a03ded971f，comparison.json SHAa41f686bdc158e20e36a1b1973a42ca367f2fde973148941f1779e8309c4250d，template SHAad78d358cc0a855fe639d051144146631aab0d541f49fc498561bdecdf99b666。证据 `artifacts/detail-temporal-validation/pilot-comparison-browser-report.json`、1366/390截图和 `.cache/detail-pilot-comparison-final-release-generate.log`；生产工作台未改源码，无需重启。

已向用户汇报现在可同页核对原两例和下载记录、新版暂无真实结果、无新增费用；下一动作保存此源码/验证检查点，运行一次完整verify，更新通俗报告和使用指南，再普通推送已授权分支并独立核对远端。旧unknown与F006/F009/F010不变；新v4授权待答，额度提醒不构成发送或新增预算授权。

以下是此前节点记录，不能代替本段最新状态。

额度恢复接续：用户新Goal明确继续开发迭代；上个worker因usage limit终止但已落script/tests/own sprint，未提交。root重新核对worktree原基线a424ef4与三个未提交文件，恢复同agent完成最终验证/提交，不重启任务或覆盖源代码。当前源码包含旧同版matcher完整result一致性和report/case/match null质量字段，但该新补丁不得引用首次16通过作为最终结果。root源码初审反例已交worker，reviewer在只读复核。根源数据来源审计重新通过，仍旧partial/new unverified、3 accept+1 reject仅旧描述、0发送/预算变更；浏览器核对脚本已准备在ignored artifacts/detail-temporal-validation/check-pilot-comparison-browser.py，待生成真实产物后运行。生产原PID均不存在，正常恢复服务并实读原结果，不盲停进程；最终验证节点另补。

2026-10-06用户最新额度提示15%，要求准备阶段汇报，未要求停工。root已核对工作树0a97abb干净、冻结proposal SHA不变、0新paidRequests、executionAuthorized=false、原report SHA不变和生产35992健康；上一goal turn为已验证功能交付的实际进展。当前worker接口已定，尚无可用生成结果/新验证，不能写成页面已完成；阶段报告report-2026-10-06-stage-progress.md按此事实保存。下一节点等worker提交其独占文件后审核/定向/实际生成，不复制未验收口头结果为通过。

必要反例：错误proposal SHA/case/run/request/帧ID源时间hash拒绝；v4缺结果保持未执行；旧反馈仅贴原结果；HTML文字安全；输出不覆盖来源；人工字段默认null；真实源表/侧车/账本/反馈/proposal前后不变。生成页面在1366桌面/390手机核对原六图和布局。相同query的新匹配只有新结果存在时计算，不能用模型工程fixture替代真实效果。

已有工作台实现未改，本切片完整验证仍以1661/1skip检查点为基线；新增生成器先做针对其来源绑定与只读行为的检查。进展与下一动作随节点追加，当前worker在实现独占三个文件。新v4授权继续待答，不能因旧预算有余额再调用。
