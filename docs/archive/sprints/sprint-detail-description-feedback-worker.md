# 已有描述级人工反馈 Worker

2026-10-06；owner detail_cost_history；独立`.worktrees/detail-feedback` / `codex/detail-feedback`，基线06f6c66。仅独占新application/detail_description_feedback.py、新tests/test_detail_description_feedback.py和本文；root负责reader/UI/共享记录。旧query-draft和cost worktrees冻结，不回写。

## 给用户的作用与下一步

工作台将能显示用户已经接受的35–36秒三个描述，以及28–29秒物品被误认成人物的拒绝结论；无需重复核对这些条目。反馈只跟当时的精确模型结果走，换版本或重做结果不能沿用旧通过标记。其他描述仍为未评判，描述正确不能扩大为所有属性、动作或检索质量已经通过。

本worker先提供无I/O的解码和投影；root再接只读文件入口与页面。当前无Provider、HTTP、DB、预算或结果改写。

## 接口与实施前自审

`decode_description_feedback(text: str) -> DescriptionFeedback`严格读取已有detail-pilot-human-feedback-v1记录，DTO冻结且不可变。字段schema_version/recorded_on/pilot_report_sha256/cases/unmentioned_entries/phase0_quality_gate/new_provider_calls；每个case保留原case/run/event/request/payload身份、scope、targets、verdict、source和statement。

`project_description_feedback(feedback, *, pilot_report_sha256, run_id, event_id, request_hash, detail: CandidateDetail) -> tuple[DescriptionReview, ...]`仅返回当前结果明确评判的逐shot/actor条目，保留来源、日期、报告SHA与原句。未返回的目标仍是unreviewed，不造肯定标签。

报告SHA失配明确报错；detail与caller run/event失配明确报错。当前payload由已有payload_hash(detail)计算，不接收caller提供的假payload。跨run/event/request/payload均不复用；只对精确命中记录检查目标实际存在，旧结果目标不能错误阻塞新结果未评判显示。

- 1MiB UTF-8字节、128记录、每记录1–8明确目标、每说明1–2048字符；不截断或遗漏原句。
- JSON重复字段、重复case、同精确结果目标重复或矛盾结论均拒绝，不依赖后者覆盖前者。
- scope只actor-description，source只direct-project-user-feedback；unmentionedEntries固定unreviewed，phase0QualityGate只能null，newProviderCalls只能非bool的int 0。
- 身份、lowercase SHA和真实ISO日期明确核验；statement只保留不解释，其Unicode/HTML内容交由root作为文本安全显示。
- 三个DTO保持不可变；不修改CandidateDetail或全局状态，不写文件、不导入Infrastructure，不扩展F006/F009/F010验收。

已读AGENTS/HANDOFF/agent-workflow、任务surface计划和既有ignored反馈，init -CheckOnly当前11项通过；接口已向root确认。接下来补精确匹配与损坏/隔离反例，定向Ruff/mypy/pytest验证后提交owned三文件供root集成。

## 已完成、已汇报与验证

现在已有用户判断可以准确带回当时的描述：三个明确接受目标与一个拒绝目标逐条投影，未提及的描述没有标签；即使说明文字说“全部正确”，也只标明确target。换run、event、request或实际payload的结果都不会继承旧判断。报告SHA失配、当前目标不存在、重复或矛盾结论会报错，不能假装没有问题或用户通过。通用合法目标名称shot-1/left与真实s1/a1均支持；跨shot同actor ID也不会串标。

新增**111项**回归，覆盖三接受/一拒绝、同镜头不同主体的混合判断和未评判、跨镜头同ID、四重身份和新profile隔离、当前不存在目标与旧payload目标区别、后续目标坏不能返回前半判断、转义后重复JSON字段、重复/矛盾报告、字段/日期/hash/source/scope/type严格校验、bool冒int拒绝、128/129记录、8/9目标、2048/2049说明、1MiB UTF-8上限、Unicode/HTML原文、不可变与零文件/DB/network I/O。statement仅保存原句，不用其文字推断额外通过。

先dot-source根scripts/env.ps1，root .venv Python -B，own src PYTHONPATH及预建.cache/feedback-{ruff,mypy,runs,pytest-cache}，没有安装或全局设置。联合命令：

```powershell
G:\Tools\ChatGPTRepo\GameingCreatorAgent\.venv\Scripts\python.exe -B -m pytest tests/test_detail_description_feedback.py tests/test_actor_details.py tests/test_architecture.py --basetemp=.cache/feedback-runs/regression -o cache_dir=.cache/feedback-pytest-cache --tb=short -W error
```

结果**187 passed / 0 skip，0.46s，警告作错误**；Ruff两文件格式/lint、Application模块mypy及git diff --check通过。首轮104/107通过，三个失败均为新测试夹具问题：中文JSON转义把组合上限夹具撑过字节上限，helper对非法detail输入先做了默认替换/取字段；改成原生UTF-8夹具和直接调用非法输入检查后通过，没有放松实现校验。

额外只读解码原ignored反馈，确认**2 cases、3描述接受、1描述拒绝**、scope只有actor-description、qualityGate=None、新ProviderCalls=0。源human-feedback.json SHA `3e905114975a5a566c1cfe8af4932cda593013d7f357a1fdce7d002b507fe5aa`及pilot-report SHA `367bbc2eb270fa8c859962804392decd6c4494af4b05abc4adef3d17385ccfec`前后一致。未导入或改写旧artifact/model/DB；固定文件reader和新独立namespace导入由root负责，不在此模块。

只读同伴复查核心身份和payload复用规则，无阻断问题；其建议的同shot混合结论、跨shot同ID、旧payload坏目标与当前坏目标区别、后续目标损坏、范围不扩大、边界和重复字段已进入回归。已向root用通俗语言报告使用帮助、实际解码和测试证据、限制及下一步。

## 交接与剩余限制

这是让已经收到的人工判断可见，不会提高模型视觉能力、改变matcher、匹配排名或把描述接受算作属性/动作/U10验收。新v3/v4或重做payload没有相应人工反馈时仍未评判；F006/F009/F010和旧未知预算保留。真实页面和固定路径reader尚由root接续验证，本worker不把纯测试当作页面已交付。

下一步root合入三文件，接只读reader/API/描述标记，核对原三接受/一拒绝及切profile不串标，再运行浏览器与完整verify、同步共享HANDOFF和用户汇报。本worker提交后冻结新worktree，旧worktrees仍冻结，未发送任何新模型请求。
