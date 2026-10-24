# Sprint：冻结计划绑定素材盘点（benchmark-freeze-v2）

更新：2026-10-24，Phase 0，main，Claude Code本机会话。规划：gc-architect角色（工作流外子Agent，请求opus，只读）；主控持久化本合同。无新录像／图片／付费API，不代填人工分组。

## 为什么做

[素材盘点](sprint-source-footage-overlap.md)已能给出“不同文件共用画面”的证据，但只是供人查看。F006要求按原录制会话分组且不能用同源剪辑凑数；冻结检查目前只拦“同SHA分到不同组”。本sprint让盘点报告成为正式冻结的可核对输入，把“共用画面却分到不同组／跨开发与测试”变成就绪阻断项。分组仍由用户决定。

## 关键约束（架构评估结论）

- `preparation_status`不能原地改：`infrastructure/benchmark_preparation_files.py:142`读取冻结时重算并要求与保存的`preparation`完全相等；原片参考页也从`freeze_document`重建上下文比较（`application/benchmark_reference_review.py:60,74,109-110`）。新增阻断会让旧冻结与已存参考页不可读。
- 因此新增`benchmark-freeze-v2`；`FREEZE_VERSION`、v1的`preparation_status`与`freeze_document`（`application/benchmark_preparation.py:14,168-225,228-272`）字节不变。本仓库3个已存freeze.json均为v1且均未`readyForIndependentEvaluation`，保留v1规则不开辟“独立测试集”捷径。
- `bind_manifest`在`benchmark_preparation.py:280`重算就绪并决定`independentTestSet`（`:323-324`），须改为按版本取就绪状态，否则v2阻断会被绕过。
- v2就绪只能由冻结包内的报告字节与冻结来源推出，不依赖当前检测默认参数。

## 合同

1. `freeze-benchmark`新增可选`--inventory <json>`（4 MiB上限，沿用有界读取）；`scripts/prepare-benchmark.ps1`新增`-InventoryPath`（仅Freeze）。新冻结一律写v2；未提供报告时`sourceInventory`为null并得到阻断。
2. 新application模块`benchmark_inventory_binding.py`（无I/O）：严格解析`source-inventory-v1`（字段集、版本、`humanDecisionRequired`为true、`limitations`与生成端`LIMITATIONS`完全一致、SHA格式、sourceId唯一、候选引用已知来源）；冻结来源按sha256匹配盘点来源（同SHA不同durationUs为硬输入错误），失败来源无SHA时按不区分大小写路径匹配。
3. v2冻结包原样保存报告为`source-inventory.json`（回执列3个文件；v1仍须恰好2个），`write_freeze`冻结期间报告变化即拒绝；派生`sourceInventory`：报告SHA／版本／parameters／ffmpegVersion、每个冻结来源`{id,status: compared|notComparable|failed|absent, inventorySourceIds}`、映射到冻结id的共用画面对（偏移、票数、log10p）、涉及计划外来源的证据数、`limitations`、`humanDecisionRequired: true`、`absenceIsNotIndependence: true`。`read_freeze`重建并要求相等。
4. v2新增阻断（在v1集合之上，记录于`preparation`）：`source_inventory_missing`、`source_inventory_incomplete`（absent／failed）、`source_inventory_not_comparable`、`shared_footage_has_different_recording_groups`、`shared_footage_crosses_partitions`。均不分配组；CLI与工作台把“未发现证据”显示为“无证据”，不是“独立”。
5. 工作台：冻结步骤可选上传盘点JSON（`ui/benchmark_workflow.py`沿用inputText模式），页面显示覆盖表与限制文案、`source-inventory.json`链接；旧v1冻结标注“未核对素材盘点”。
6. 不改：绑定选项、绑定运行核对、原片参考页、`acceptance_readiness.py`。

## 文件归属（单一实现者）

新建`src/gamingcreator/application/benchmark_inventory_binding.py`、`tests/test_benchmark_inventory_binding.py`；修改`application/benchmark_preparation.py`、`infrastructure/benchmark_preparation_files.py`、`cli/main.py`（仅freeze部分）、`scripts/prepare-benchmark.ps1`、`ui/benchmark_workflow.py`、`ui/static/benchmark-workflow.js`、`tests/test_benchmark_preparation.py`、工作台HTTP测试、`docs/references/benchmark-preparation-guide.md`、`docs/references/source-inventory-guide.md`。主控负责本sprint、HANDOFF／progress／assignments／human-inputs与提交。

## 验收

- 旧冻结回归：用固定夹具与未改`freeze_document`生成v1并钉住freeze.json SHA256；`read_freeze`可读、重绑benchmark.json一致，原参考页测试不改即通过。
- v1回执3文件拒绝；v2缺`sourceInventory`拒绝。
- v2：无报告→missing；全覆盖无证据→无盘点阻断；共用对同组同分区→无阻断；异组或跨分区→对应阻断；notComparable／失败（按路径）／缺失→对应阻断；同SHA异时长拒绝；篡改报告或`sourceInventory`→`read_freeze`拒绝；有盘点阻断的v2绑定`independentTestSet`为false。
- CLI、PowerShell参数、工作台冻结步骤有／无盘点文件；手工只读`read_freeze`本仓库3个已存冻结。
- 定向测试、Ruff、mypy通过；任何既有v1冻结或参考上下文读失败即停止回退。独立评估：code-quality-guard（验收状态／身份绑定边界）。

## 风险

旧v1永远“未核对盘点”；`limitations`严格相等意味着文案修改需`source-inventory-v2`；候选极多的报告可能超4 MiB被拒（明示不静默放宽）；SHA匹配意味着重编码副本视为absent，须对冻结原字节重跑盘点。就绪仍不等于独立性证明，十槽≥70%质量门槛在人评前保持null。

## 结果

- 规划：gc-architect（请求opus，只读）给出v2方案；实现：gc-coder（请求sonnet，转录175条回复为claude-sonnet-5-5）；评估：code-quality-guard（请求opus，只读）。
- 实现：新`application/benchmark_inventory_binding.py`（严格解析、按SHA／失败按路径匹配、派生`sourceInventory`、v2阻断）；`benchmark_preparation.py`新增`FREEZE_VERSION_V2`／`preparation_status_v2`／`freeze_document_v2`／按版本取就绪；`benchmark_preparation_files.py`写入重读报告、版本区分回执2／3文件、读取重建比较；CLI `--inventory`、`prepare-benchmark.ps1 -InventoryPath`、工作台冻结步骤可选上传与覆盖表。
- 独立评估PASS（无P0／P1）：15个变异中13个被测试发现；两处防御检查无测试已补（主控另行把“回执缺报告文件”检查删去复验，新测试`forged_without_file`随即失败）。评估发现一致改写多文件可把被阻断的v2伪造成v1，据此加固：**v1冻结绑定一律`independentTestSet=false`**，独立测试集只能来自盘点完整的v2；指南写明回执只能发现不一致修改、不是认证，以及BOM另存会改变报告SHA。
- 验证：定向14文件326项全部通过（-W error），ruff check／format（251文件）／mypy（119源文件）通过；5个已存v1冻结改动前后读取结果与SHA逐字一致；v1固定SHA测试`444c176f…1109`经评估者用HEAD旧代码复算一致。真实试跑：试点计划＋17素材盘点冻结为v2（1来源已比较、0对）；把Atom PV／实机分到不同组的反例得到`shared_footage_has_different_recording_groups`。
- 未做：本次未重跑完整verify；PowerShell参数无脚本级测试（已实跑）。
