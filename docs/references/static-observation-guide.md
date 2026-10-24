# 独立静态观察的本地导入和条件搜索

这组开发CLI保存已有注册帧上的结构化外观声明，让没有动作事件的画面也能独立搜索。新的[单帧自动生成入口](static-observation-generation-guide.md)另有具体授权和恢复流程，当前验证见对应sprint；这里仍按原格式导入，没有通用旧Provider输出转换器。当前不需要用户重标、手填新表或重跑录像。普通工作台搜索与原候选精分析保持原流程。

## 显式选择来源和版本

来源必须是已有Completed run，且通过源录像／注册证据完整性与覆盖资格检查。导入和搜索都重验，带缺口的长钟馗run仍不可用。每个run内用明确collectionId区分一个不可变声明包；查询不挑最新，也不合并不同collection。

在项目根目录使用隔离环境：

```powershell
. ./scripts/env.ps1
./.venv/Scripts/python.exe -B -m gamingcreator import-static-observations --project <project> --run <completed-run-id> --collection look-1 --input <package.json>
./.venv/Scripts/python.exe -B -m gamingcreator search-static-observations --project <project> --run <completed-run-id> --collection look-1 --input <query.json>
```

成功返回JSON；输入／版本／scope错误退出2，静态库身份／冲突／损坏／路径错误退出5。非Completed和coverage-gap沿用原错误码。新库固定为project内`static-observations.sqlite3`，原`timeline.sqlite3`只读；不产生模型调用、预留或来源费用结算。相同canonical包返回unchanged；同collection不同内容拒绝，改版另选collectionId。

## 包与查询格式

以下是开发格式示例，身份／hash均为占位值，不能用于真实来源或当真人参考。生产声明应由其来源工具输出精确绑定值。

```json
{
  "schemaVersion": "static-observation-import-v1",
  "runId": "run-1",
  "collectionId": "look-1",
  "mediaId": "media-1",
  "sourceSha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "configHash": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "pipelineVersion": "fixture-pipeline-v1",
  "provenance": {
    "sourceNote": "Synthetic declaration example; visual judgment unverified.",
    "sourcePayloadSha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
    "sourcePayloadVersion": "example-v1"
  },
  "observations": [{
    "localObservationId": "obs-1",
    "evidenceId": "run-1:media-1:image:000000",
    "actors": [{
      "actorId": "actor-a",
      "attributes": [
        {"partGroup":"source-head","partId":"head","kind":"hair_color","value":"white","status":"observed"},
        {"partGroup":"source-body","partId":"coat","kind":"clothing_color","value":"blue","status":"observed"},
        {"partGroup":"source-body","partId":"coat","kind":"clothing_shape","value":"coat","status":"observed"}
      ]
    }]
  }]
}
```

可选`pipelineHash`提供时必须精确匹配原run；configHash和pipelineVersion必填。每条观察只引用一个已注册图像，包不接收任意路径、模型自算时间或原event/candidate身份。范围由注册时刻计算。UTF-8无BOM，最大1MiB／128观察／每观察8主体／每主体16属性，重复键、额外字段、未知版本明确拒绝。

```json
{
  "schemaVersion": "static-observation-query-v1",
  "actorAll": [
    {"kind":"hair_color","value":"white","partGroup":"hair"},
    {"kind":"clothing_color","value":"blue","partGroup":"garment"},
    {"kind":"clothing_shape","value":"coat","partGroup":"garment"}
  ]
}
```

查询可省runId／collectionId，由CLI明确绑定；若提供则须一致。也支持原`actor-detail-query-schema-v1`／`actor-detail-query-v1`／冻结词表的完整typed manifest，environmentAll须为空。只支持hair_color、clothing_color、clothing_shape、held_shape、held_class，不接受action／effect／environment或自由文本。

查询partGroup是局部绑定名：同组条件必须落在同一真实partId，可一致改名，无需与来源partGroup同名。所有条件须在同一个actor、同一个帧成立。uncertain／缺失不提供支持，同part互斥观察不能完整命中；只返回完整声明支持，尚无partial界面。当前同actor上相同kind/value的uncertain会保守阻断，不声称已完成通用人物理解。

## 阅读结果

matches包含`kind=static_appearance`、独立observationId、actorId、注册帧路径／hash／源微秒和`[t,t+1)`、原片路径及supportedAttributes。结果按源时间／观察ID／主体稳定排序，不进入默认动作搜索、选片篮或benchmark。

provenance和sourcePayloadSha256只是来源声明，不认证Provider或真实画面。`visualVerified/humanLabels/qualityGate`恒null，来源费用unknown；`paidRequestsSent=0`仅表示本地操作零新增请求。旧候选报告的`independentStaticClothingIndex=false`继续描述其旧候选路径，不代表此新CLI自动接入其中。

2026-10-24工程验证为202通过／1符号链接权限skip、静态检查与独立评估通过；真实视觉准确性和F006/F009/F010均未通过。见[报告](../exec-plans/report-2026-10-24-static-observation-index.md)。
