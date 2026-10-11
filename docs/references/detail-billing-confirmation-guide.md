# 精分析失败请求的人工账单确认

当API没有给出费用，但你已经去控制台核实“这次没有扣费”，可以为**指定的一次尝试**保存人工确认。工作台的“精分析费用与调用”会同时显示原API未知／保守占用、人工已核实未扣费，以及核对后占用。基础分析和其他项目不混入这里。

这不是商业计费或自动退款功能。原API记录、账本、请求和发送上限保持；核对后金额不授予新模型调用权限。当前仅支持已结束、API费用未知、人工明确零扣费的记录；同一材料重放无新增效果，冲突材料拒绝，不能凭同一个请求哈希核销它的所有重试。

使用项目隔离环境运行：

```powershell
./scripts/confirm-detail-billing.ps1 -Project <项目目录> -Run <运行ID> -Budget <预算ID> -Request <请求哈希> -Attempt 1 -Material <确认材料.json>
```

`-Json`输出可保存的核对结果。材料为`detail-billing-zero-confirmation-material-v1`，严格包含projectPath、runId、budgetId、requestHash、attemptNo、requestSha256、plannedSha256、resultSha256、confirmedCostCny="0"、statement、source、confirmedAtUtc，以及schemaVersion。前三个SHA分别绑定原request.json、该attempt的planned/result原始字节；statement保留真人原答，source保留材料来源，时间须带UTC时区。明确核对身份再生成材料，不凭缺失字段猜测。完整字段见application/detail_billing_confirmation.py。

导入记录不可变并保存材料全文与SHA；读回重新核对原证据。材料／项目链接路径、重复字段、错身份、进行中、已知API费用、证据漂移或冲突均拒绝，不减少占用。原始账单确认材料也要保留；不能把新生成的声明冒称Provider账单接口的验票。

2026-10-11已根据你的原答，准确映射并导入2026-10-08两个HTTP400的零扣费确认，各一次。工作台展示释放预留¥4.065536、核对后占用¥0.04673416；更早基础分析未知费用与新v5估算保持。你无需再运行导入或重复核对。[本轮合同](../exec-plans/sprint-detail-billing-confirmation.md)记录独立验收与真实读回；新增材料只用于以后明确核实的指定请求。
