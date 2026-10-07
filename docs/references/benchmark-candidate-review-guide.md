# 回看固定检索候选，保存人工评分

这条流程把一次已保存的检索结果做成本机评审页。你可以按原排名回看片段，填写评分和理由，下载保存，之后载入继续填写。每个查询始终保留十个位置；缺位和已知重复不会被后面的结果补上。页面和导入工具不会自动替你判分。

先按[验收准备指南](./benchmark-preparation-guide.md)冻结素材、查询和人工参考，再绑定已完成分析。正式验收仍需事前确认的独立录像和人工参考；已经看过结果的开发录像可用于练习流程。

## 取得带保存身份的报告

在仓库根目录执行一次明确的本地检索评测：

```powershell
. ./scripts/env.ps1
./.venv/Scripts/python.exe -B -m gamingcreator benchmark --input artifacts/acceptance-bound-001/benchmark.json --binding artifacts/acceptance-bound-001 --project artifacts/demo-phase0 --mode hybrid --output artifacts/acceptance-ranking-report.json
```

这一步按冻结查询检索并保存普通检索记录；hybrid使用已有本地语义模型，lexical只按文字检索，不会触发新的视觉分析或上传。未填写评分时退出6并保留报告，表示“验收未验证”。报告中每条成功查询的retrievalId指向实际保存排名。旧报告缺身份时工具拒绝准备，须明确生成一次新报告，不能猜测对应历史结果。

## 打开评审页

使用已有PowerShell 7：

```powershell
./scripts/prepare-benchmark-review.ps1 -Project artifacts/demo-phase0 -ReportPath artifacts/acceptance-ranking-report.json -BindingDirectory artifacts/acceptance-bound-001 -OutputDirectory artifacts/acceptance-review-001
```

输出必须是新目录，不能覆盖原项目、报告、绑定或记录。打开其中review.html，保留原素材在本机。工具只读核对Completed来源、录像和证据、原配置及保存的排名和区间；准备页面本身不搜索、不加载模型、不操作预算。

每个位置显示原排名、原区间和模型描述。“播放此区间”定位本机原片，到末尾暂停，桌面和窄屏均可使用。当前验证三个零起点MP4；浏览器不支持编码时提示用本机播放器核对。非零源起点自动对齐仍待TD006验证，暂用手动回看。浏览器暂停可能略晚于末尾，评分依据和导出边界仍是显示的原微秒区间，不能视为逐帧裁切。

## 填写与继续

先填日期和填写人，再根据实际回看选择：

| 评分 | 含义 |
| --- | --- |
| 未判定 | 暂不下结论，可以先记备注 |
| 0 | 无关 |
| 1 | 相关，但这段不能用于查询要求 |
| 2 | 可用 |
| 3 | 高度相关 |

评分必须写理由；2/3还须选择该查询事前冻结的独立事件。多个候选实际是同一次动作时选择同一humanEventId，正式计分按原协议去重。没有事前参考时2/3不可选择，可留空或记录0/1，不能事后补造参考。已知同事件重复位置没有第二套评分入口；失败查询明确显示失败，不能当成功但零命中。

点击“下载当前记录”保存JSON，再用“继续填写已有记录”载入。空记录可下载，评分保持空。文件不对应时拒绝载入并保留当前输入；载入期间有新编辑也保留新编辑。关闭页面前须下载，页面没有自动保存或云同步。“已由人复核”只记复核状态，不改变原参考确认或独立测试声明，页面不计算质量结论。

## 导入记录并生成评测文件

```powershell
./scripts/prepare-benchmark-review.ps1 -Project artifacts/demo-phase0 -ReportPath artifacts/acceptance-ranking-report.json -BindingDirectory artifacts/acceptance-bound-001 -RecordPath artifacts/benchmark-review-record.json -OutputDirectory artifacts/acceptance-reviewed-001
```

工具再次核对绑定、报告、原素材及保存检索；改动查询、位置、候选、区间或冻结依据会被拒绝。新目录保存原输入、规范记录、benchmark-judged.json及SHA回执；只有实际评分进入candidateLabels，备注和未判定不变成标签。完成回执最后保存，中途未完成须换新目录。

要计算这次回看过的固定原排名，导入时加-Score：

```powershell
./scripts/prepare-benchmark-review.ps1 -Project artifacts/demo-phase0 -ReportPath artifacts/acceptance-ranking-report.json -BindingDirectory artifacts/acceptance-bound-001 -RecordPath artifacts/benchmark-review-record.json -Score -OutputDirectory artifacts/acceptance-fixed-score-001
```

输出benchmark-fixed-report.json，使用同一份原十位结果及原benchmark评分标准，不重新搜索。原失败查询保持失败，缺位和重复仍计入十位分母；尚未判断的位置或没有确认的原参考，不会变成已评分。资料独立性和原参考确认无法事后升级。全部符合原门槛时qualityGate=true；未达标为false、未验证为null，两者均退出6，报告仍完整保存。新目录与资料核对规则和普通导入相同；-Score必须有-RecordPath。

报告保留原retrievalId、startedAt、elapsedMs及retrievalWallclockToSourceRatio；scoredAt和scoringElapsedMs单独记录计分时间，读回的速度不能冒充原检索速度。scoring记录原报告／绑定／规范人工记录及固定依据SHA，ordinarySearches和paidRequestsSent均为0。费用从已核对原分析attempt汇总，忽略下载记录和报告中自行填写的费用声明；未知仍未知，原账本不操作。它沿用基础分析费用范围，不含独立精分析或其他项目的预留。

不加-Score时仍只导出标签，qualityGate始终null。若要明确重新检索比较，可继续用原benchmark入口：

```powershell
. ./scripts/env.ps1
./.venv/Scripts/python.exe -B -m gamingcreator benchmark --input artifacts/acceptance-reviewed-001/benchmark-judged.json --binding artifacts/acceptance-bound-001 --project artifacts/demo-phase0 --mode hybrid --output artifacts/acceptance-final-report.json
```

上面benchmark命令重新执行冻结查询并产生普通检索记录，须保持相同配置，其结果不是原排名只读计分。两个计分入口都遵循[原70%协议](./phase-0-benchmark.md)。普通准备／导入与文件发布回执本身不计算质量；显式-Score的结果和benchmark-fixed-report.json才提供固定排名计分结论。

本机演示位于ignored artifacts/benchmark-candidate-review-validation/评审页面/review.html，使用已有三份开发录像，未填真实评分，不是独立验收样本。页面含本机路径和模型描述，留在本地；原视频、数据库和生成文件不随Git提交。
