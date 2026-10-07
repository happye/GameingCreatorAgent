# 登记验收录像，先冻结查询再评测

这条流程用于Phase 0的真实检索验收准备。先记录验收录像、同源关系、查询及人工参考，再分析或查看模型结果；后来按录像身份绑定已完成分析，交给现有benchmark。它只准备本机资料，不抽帧、不分析、不检索或上传画面。缺资料能保存草稿，但不能成为独立验收通过结论。

## 1. 填写计划

复制[计划模板](../../templates/phase0-benchmark-plan.example.json)，保存为本地JSON。模板中的路径需要换成真实录像；相对路径以计划文件所在目录为起点。修改来源／查询只能创建一份新冻结资料。

| 字段 | 怎么填 |
| --- | --- |
| datasetId | 本次数据集的固定名称 |
| labelVersion | 人工参考版本；尚未标注用null |
| humanReferences | confirmed仅在人工参考实际确认后填true；annotators填写人，reviewed记录是否复核 |
| sources.id/path | 唯一素材ID与原本地文件路径 |
| recordingGroup | 原始录制会话。同一PV的版本／剪辑保守放同组；不知道时null，不能当独立会话 |
| partition | development用于开发；test用于独立测试；同录制组不能跨区 |
| modelResultsViewed | 如实记录是否看过模型结果；测试录像已看过结果便不具备本次独立性 |
| queries.id/text/sourceId | 固定查询ID、原文与该查询对应的素材ID |
| queries.family | 同一查询及改写的族；不能把改写分别放在开发与测试区 |
| kind/referenceEvents | main至少10个独立可用人工参考；sparse为1–9个；negative为0个。参考字段沿用[原评测格式](./benchmark-manifest-schema.md) |

人工参考由人观看原片填写，使用独立humanEventId／independenceGroup、usableRanges和reason；时间为原录像微秒。尚未填写可用空数组，confirmed=false。计划不接受候选评分，因为此时尚未查看检索结果。

## 2. 冻结本地资料

在仓库根目录，用已有PowerShell 7：

```powershell
./scripts/prepare-benchmark.ps1 -InputPath artifacts/acceptance-plan.json -OutputDirectory artifacts/acceptance-freeze-001
```

程序本地探测并核对原视频SHA和时长，保存原输入字节、规范计划、实际来源、冻结时间及准备缺口。输出必须是新目录，不覆盖旧冻结；完成回执最后写入，中断留下的目录不能作为完整冻结读取，另用新目录重做。

准备状态检查至少10个已知录制组和不同内容、推荐10–20段代表录像；录制组／相同内容／查询族跨区、同内容被登记不同录制组、测试已看结果、测试素材无查询、缺主查询或人工参考等会明确列出。结构错误、参考区间越界或冻结期间文件改变则拒绝保存。原录制独立性及人工声明由填写人负责，工具记录声明，不能鉴定视频是否真的独立或替人标注。

查看preparation.readyForIndependentEvaluation和blockers；即使准备完成，qualityGate仍为null。路径／文件哈希和冻结时间证明本机这次保存的内容，回执用于后续一致性检查，不是对人工声明的认证。没有API密钥也能执行；这里没有新的费用授权。

## 3. 绑定已完成的分析

分析沿原入口单独执行，需要原有模型、上传与费用授权。准备一个本地运行映射JSON，例如：

```json
{"test-001": "真实的Completed运行ID"}
```

映射必须完整且仅含所选分区中被查询的素材，来源都在同一项目；同内容不能用多个别名／run重复计入。再执行：

```powershell
./scripts/prepare-benchmark.ps1 -Action Bind -FreezeDirectory artifacts/acceptance-freeze-001 -Project artifacts/demo-phase0 -RunsPath artifacts/acceptance-runs.json -Partition test -OutputDirectory artifacts/acceptance-bound-001
```

绑定核对Completed run及原文件／证据完整性，并比较冻结SHA与时长。新目录保存benchmark.json、binding.json和回执；不写项目，不执行搜索。开发流程用-Partition development，输出不会声明独立测试。

人工参考不足时，生成的humanLabels.confirmed保持false；独立准备有任何缺口时independentTestSet=false。候选candidateLabels始终空，需要后续实际回看再填写。原人工确认已为true但候选未评分，也不代表检索质量通过。

## 4. 在固定依据下运行和填候选评分

可用[固定候选评审页](./benchmark-candidate-review-guide.md)回看、填写理由、下载并继续已有记录；准备页从带retrievalId的新报告核对实际保存排名，导入后生成原v1判分文件，不替人评分或确认独立性。

复制bound目录中的benchmark.json到另一文件，保留原绑定目录。先在固定查询下检索，再按[人工验收指南](./human-acceptance-guide.md)观看返回原区间，填写candidateLabels的0–3评分、理由及独立humanEventId。不得在看过结果后把未确认的原参考或不独立数据改成已确认／独立。

```powershell
. ./scripts/env.ps1
./.venv/Scripts/python.exe -B -m gamingcreator benchmark --input artifacts/acceptance-judged.json --project artifacts/demo-phase0 --output artifacts/acceptance-report.json --binding artifacts/acceptance-bound-001
```

--binding在打开项目和加载检索模型前复核原绑定：只允许追加／修改candidateLabels与humanLabels.reviewed。改查询、参考、来源、标签版本、填写人或原确认／独立性声明会拒绝，必须重新准备并披露独立性。旧benchmark不传此参数仍按原合同运行；正式冻结流程应传它。benchmark会执行本地检索并保存检索记录，与前面只读准备／绑定不同；不增加付费模型请求。门槛未通过或缺人评时保留报告并退出6。

仍按十个固定位置、重复与缺位计零、每个主查询至少70%执行。当前已有开发PV与流程核验不能充作正式独立验收；本轮不要求你立即补齐素材或评分，先让工具流程可用。
