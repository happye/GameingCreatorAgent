# 指定失败请求的人工费用核对

2026-10-11，Phase 0／F003／F004。用户已恢复开发，主线v5有界试验由root另行执行；本合同是独立费用持久化交付，不代替真实理解验收，不改冻结v5请求或原预算。harness_planner已只读给出合同，Sol/medium实际执行元数据已核对。task_quality_guard为唯一独立评估角色，先对齐合同再评价实现；不另叠加reviewer。root持有公共记录和真实材料，Generator使用独立worktree。

## 使用效果与范围

在已有费用历史中明确分开“API费用未知”“人工已确认未扣费”“原保守占用”和“核对后占用”。用户确认只针对指定失败请求，不因为同一个请求曾重试就连带清除其他尝试。新核对金额不代表获得新调用授权；本阶段不做商业计费、退款、撤销或自动发送。

首版仅接受已结束、原Provider费用未知且明确人工确认零扣费的attempt。新增版本化追加确认记录与只读汇总，不改ProviderUsage／原ledger／冻结请求／结果／全局BudgetLedger，发送仍走原保守门禁。API unknown数量与请求／帧次数均保持。真实旧billing-confirmation材料只作已存在证据，先不导入，原费用与本次v5提案保持。

## Owner与文件

Generator负责新增application/detail_billing_confirmation.py、infrastructure/detail_billing_confirmation.py、对应tests及infrastructure/detail_cost_history.py。根路径均在src/gamingcreator下。root负责公开调用入口／用户说明、真实核对、旧素材保护及HANDOFF／assignments／progress等公共文档；不同时写Generator文件。所有写者知道他人修改并保留，独立worktree，不递归委派。

## 验收合同

导入显式指定project、runId、budgetId、requestHash、attemptNo；核对原request／planned／result、其hash、终态及未知用量。确认材料保留SHA、原答、来源和时间，不冒称Provider接口验票。每attempt一个不可变确认，在现有预算写锁内重读；相同内容幂等、冲突拒绝，锁忙不重试、未原子发布的临时记录不计数。

不存在／错身份／跨项目／孤儿／进行中／已有API结算／证据漂移／非零或非有限金额／重复字段／越界大小／链接路径均拒绝，不减少占用。读取保持原历史字段，额外返回人工确认、释放预留和核对后占用；只有明确提供既有上限才计算余额，不猜余额、赤字不隐藏。

合成两HTTP400尝试核对释放合计¥4.065536，另一unknown与已知费用不变；覆盖第二进程、并发／幂等／冲突、损坏与写入中断，证明旧文件逐字节不变、只读零写入／零Provider。相关费用／sidecar／恢复测试及Ruff／mypy，原阶段验收状态不变。任何需要改发送门禁、身份歧义或无法解释的费用冲突停止实现并返root，不反复试错。

合同已由唯一task_quality_guard对齐通过，Generator已在独立worktree实现并验证中；root的两次v5请求已执行完。当前无真实账单导入／原ledger改写。下一步收取Generator的指定文件提交、同一guard独立验收，root补公开入口与真实确认的显式映射；任何证据歧义拒绝导入，不扩大成发送预算授权。
