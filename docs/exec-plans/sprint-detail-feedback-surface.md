# 将已有人工描述反馈带回工作台

2026-10-06，root / Codex，codex/visual-details。查询草稿1457/1权限skip完整验证完成，本地714e346；push两次和ls-remote均GitHub443失败，新远端未确认。新v4两次调用授权仍待明确答复，本切片保持离线。

## 用户效果

查看旧精分析时，工作台说明35–36秒三个描述已获用户确认，28–29秒s1/a2已被用户指出物品误认，其他条目仍未评判。只确认描述，不扩展为结构属性、动作或检索质量验收；原模型输出和匹配判断保留，不悄悄抹去失败案例。

反馈必须与原run/event、精确requestHash、payloadHash、shot/actor ID和旧审核报告SHA绑定。切到v3/v4或重做模型后，不把旧判断贴到新结果。文件缺失为没有已登记反馈；损坏、冲突、错误身份须明确报错，不能无声当作用户通过。读取不运行模型，不写SQL、账本或基础事实。

## 边界与分工

第一步只做纯Application反馈解码及投影，沿用已有ignored `artifacts/detail-query-validation/human-feedback.json` 的 `detail-pilot-human-feedback-v1`，不让其变成U10标签。输入保留source/direct-project-user-feedback、scope/actor-description、recordedOn、pilotReportSha256、原句与exact targets；unmentionedEntries=unreviewed、phase0QualityGate=null、新ProviderCalls=0。上限1MiB、128记录、每组最多8个明确目标和2048字说明；拒绝重复JSON字段/目标、矛盾判断、bool冒数字、错误hash/date/字段/来源和不存在的shot/actor。

纯接口建议 `decode_description_feedback(text: str) -> DescriptionFeedback` 与 `project_description_feedback(feedback, *, pilot_report_sha256, run_id, event_id, request_hash, detail) -> tuple[DescriptionReview, ...]`。payloadHash由现有canonical_detail_json/payload_hash计算，不能信任caller给的假hash；project只投影匹配的exact key。相同run/event/request但payload变化的旧记录不复用；可以明确返回无当前反馈，不把旧判断算当前肯定。pilot报告SHA失配为损坏。返回必须保留原statement/date/source、scope以及shotId/actorId/verdict，明确描述级，不修改detail。

- detail_cost_history：新独立`.worktrees/detail-feedback` / `codex/detail-feedback`，只写新 `application/detail_description_feedback.py`、`tests/test_detail_description_feedback.py` 与own sprint。共享root venv/env.ps1 + Python -B，own缓存；其他worktrees冻结，不改UI/Provider/现有合同/公共文档。
- root：协议review与后续只读固定路径adapter、service/API/UI标记、真实旧反馈导入/只读检查、公共记录。先把纯合同集成并验证，再接页面；写入或路径变更若需要必须另明确方案，不覆盖旧反馈/报告/模型结果。

## 验证与限制

页面整合的本地路径方案：固定读取项目内`detail-description-feedback/feedback.json`与`reports/<pilotReportSha256>.json`，读取有界普通文件并拒绝链接/目录逃逸。每次inspect只加载一次，再按当前已验证CandidateDetail投影。不存在此命名空间为没有已登记反馈；目录存在但记录/报告缺失或损坏为明确409，不默默当通过。不会接受网页传入反馈路径或内容，不新增HTTP写反馈入口。

真实接入仅把已有human-feedback.json和原pilot-report.json的原始字节复制到这个新的、ignored、独立命名空间，先核对报告SHA、两真实key与payload，使用exclusive-create、不覆盖旧文件；检查源表/旧侧车/账本/原报告/原反馈前后不变。此为当前本地开发的可逆文件准备，非发送授权，也不重写模型结果。项目内新反馈文件仍不进Git；后续UI只读。

覆盖原三描述接受/一个描述拒绝、未提及条目unreviewed、跨run/event/request/payload隔离、旧反馈不能贴新profile、伪造报告SHA、矛盾及重复目标、未知scope/source、Unicode/HTML文字保留、无I/O及immutable detail。这只是让已经收到的人工纠错可见，不是增加自动视觉能力、替代人工动作/检索验收或更改排名。

## 已汇报与下一步

最终定向补强：报告worker6aa603c→18fddea已整合，76新报告反例+111纯反馈+17 HTTP/browser与相关旧检查联合 **244 passed/44.26s**，.cache/detail-description-feedback-final-targeted.log；Ruff全src/tests及reader/service mypy通过。报告validator用原始UTF8文本核验完整来源链，reader已hook；新HTTP反例正确重绑报告SHA但候选不同仍409。独立review确认来源缺口已堵，未引用的报告case不获得确认。真实probe补逐条原描述可见性后重验通过，截图已视觉核对，0调用/写账本。接下来先保存当前实现，再运行完整verify；不复用历史1457结果。

## 2026-10-06 接入检查点

纯codec/projection worker09dae6f已整合fb77ab5，111新纯测试通过。root只读reader、inspect一次加载和详情/匹配标记已完成；首次联合167 passed/43.94s。真实原反馈与报告原字节登记新独立命名空间，3 accepted/1 rejected，仅描述级；源DB/旧侧车/账本/原报告/反馈/冻结新proposal SHA不变，0新增Provider或预算变更。暂存目录rename WinError5后改exclusive-create新目录/报告先写/反馈后写，未覆盖来源或改ACL，失败暂存保留ignored。

真实1366/390页面的两组目标数量、未评判标记、原模型描述、匹配旁相同反馈、v4缺结果不借用旧结论已检查，0页面错误/外部请求/横溢。证据 artifacts/detail-temporal-validation/description-feedback-import-report.json 和 description-feedback-browser-report.json。此检查不证明模型已修复物品误认。

query_draft_review发现仅核验报告SHA不足以证明候选来自该报告；已安排同一worker在自己的worktree只新增纯 detail_description_report.py/新tests/own sprint，root后续reader hook，HTTP fixture改为具有完整身份/完成attempt/payload的报告，并增加重绑正确SHA但外来候选仍409的回归。其余旧文件冻结。完整verify尚未针对本切片运行，不使用1457历史结果冒充当前通过。

已向用户汇报真实三个确认/一个判错已可见、其他仍待核对、切版本隔离、零费用，接下来补报告来源验证、全项目检查和更新本地服务；详细最终汇报将保存report-2026-10-06-description-feedback.md。新v4发送授权仍无答复，不调用。

已向用户说明查询草稿与报告已保存、远端连接失败；下一步把明确的描述确认/判错带回工作台并隔离新结果，不重复要求用户标记同一条目。完成后按持久规则报告使用收益、实际验证、剩余问题和下一动作。新v4许可继续待答，不自动发送或释放旧未知预算。
