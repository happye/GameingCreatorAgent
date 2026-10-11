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

## 实现与验证节点

Generator已在codex/billing-confirmation-20261011提交c11ffe5，root合入887d55e；仅指定四文件，worktree干净。新增47passed／1 Windows符号链接权限skip，相关138passed／1skip、HTTP/refinement/架构14passed／1skip；Ruff／三源码mypy／脚手架通过。actual模块路径和运行时元数据均核对，harness_generator确为gpt-6.1-sol/medium，Planner同型号、guard Sol/high，不以自称作为证据。

root补公开confirm-detail-billing.py/.ps1、只读工作台呈现与指南。入口按显式project/run/budget/request/attempt转交严格材料；页面分开原API未知、人工零扣费、释放预留和核对后占用，不新增发送或导入HTTP路由。公开入口／桌面与窄屏真人确认夹具／原cost HTTP／精确comparison38passed；Ruff、90源码mypy及帮助入口通过。原无确认响应兼容，读回无写入，确认不影响API unknown计数。

真实旧原答已只读映射两请求：budget actor-detail-temporal-pilot-20261006，run96b5f01530ce43e2944828fb0520b9b4/e733a6cb…与runf601fb9b3e734d5ea188fc15c790acbb/afdc9331…，均attempt1，准确checkpoint为HTTP400；metadata记录时间及原result逐项一致。新材料保留“已核实未扣费”／原UTC／来源与原材料SHA，绑定request/planned/result字节，921旧项目文件不变。映射保存在ignored artifacts/detail-billing-validation-20261011/，**尚未真实导入**；首次辅助检查错误假定execution_details含HTTP状态、空正文是JSON，已按真实checkpoint纠正，不改原证据或重发。

原guard正在独立评估实现／实际v5执行／真实映射；只有评估通过才导入旧零扣费确认。一次完整verify已启动（exec handle23672；日志.cache/detail-billing-full-verify.log、JUnit.cache/detail-billing-full.xml），格式／lint／99类型范围已过，行为仍运行，旧workflow失败初现留待终态统计，不追修／重跑。之后双离线包／新进程读回／一次服务更新及实际页面验证；没有新费用授权或付费请求。

Planner复用只读核对当前批准计划：F001–F005技术合同及F006工具链已交付，未发现可完全绕开真实素材／真人核对／新授权而仍属计划的下一主要功能缺口。不重复开发已有验收／索引入口，不以新诊断页消耗额度；费用交付完成后下一主线是原F006独立质量验收，来源分组／事前原片参考／固定前十评分由真人提供，保持质量gate和后续正式桌面／商业阶段限制。用户“稍后核对，继续开发”已记录，当前人工判断空，不重复催促。

## 完整检查、包与现用节点

同一完整verify handle23672已终态exit1：2484项／2477passed／2failed／3error／2权限skip，JUnit602.524秒（终端602.73秒）；五旧版本选择prepare读interrupted而非finished归TD014，未改workflow或追修、未窄复查／重跑。新增58项57passed／1权限skip。201文件格式、lint、99类型范围通过；两离线wheel字节一致，SHA bf000539dc1c067a47b94046fb52338f078f655d7ca3471857501d4f13df8079，101包文件等源码，无素材／密钥／缓存混入。独立`-I`进程只从wheel导入fee模块并读真实原历史／零确认投影，原共享占用¥4.11227016保持。

真实PowerShell公开入口已用合成失败请求验证，精确确认与0新调用成功。真实导入依然0。旧服务health已拒绝连接，deploy助手在任何kill前退出，未操作旧PID；用启动助手实际新启动一次，现用PID5140／helper50496／launch20261011-163957-102-a30c7b03aa684ec1b796b51504b4f613以实际receipt为准。1366／390实际页面在两个原run读费用，静态资源等源码，新backend确返回零人工确认投影；无新搜索／修改HTTP／外部请求，921项目旧文件及40外部保护保持。

独立guard后续任务当前运行时为pending_init，非已验收；没有追加重复评估者或用主控替代签收，真实材料保持待审。下一恢复时先查该任务的实际状态，不仅因观察超时而重启；通过后按mapping-report两准确身份调用公开入口，各追加一次，再执行verify-readback.py／check-live.py（不带--before-import）及wheel新进程重读，保留原ledger与新v5费用。此前用户原答无需重问，新v5画面仍稍后核对。

功能检查点ff95517已正常push到授权GitHub/codex/visual-details，实际远端从b232013更新并用ls-remote精确读回一致；不更新main／不强推。本地工作树干净，旧network失败记录作为历史，当前publication见.cache/detail-billing-publication.json。goal保持active，后续独立评估／真实追加仍未完成，未将费用或质量gate虚标通过。
