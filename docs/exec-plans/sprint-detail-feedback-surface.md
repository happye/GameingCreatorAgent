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

覆盖原三描述接受/一个描述拒绝、未提及条目unreviewed、跨run/event/request/payload隔离、旧反馈不能贴新profile、伪造报告SHA、矛盾及重复目标、未知scope/source、Unicode/HTML文字保留、无I/O及immutable detail。这只是让已经收到的人工纠错可见，不是增加自动视觉能力、替代人工动作/检索验收或更改排名。

## 已汇报与下一步

已向用户说明查询草稿与报告已保存、远端连接失败；下一步把明确的描述确认/判错带回工作台并隔离新结果，不重复要求用户标记同一条目。完成后按持久规则报告使用收益、实际验证、剩余问题和下一动作。新v4许可继续待答，不自动发送或释放旧未知预算。
