# 独立精分析 Provider 与中断恢复

2026-10-05，root / Codex，codex/visual-details；接续8bcf1ae。按总方案的Phase 0理解/检索路径及actor-detail-matching-spec顺序推进。

## 范围与完成条件

root独占新增精分析Provider、调用记录codec、sidecar恢复/预算补充、对应测试及共享交接。其他历史worktree冻结。先完成本切片，再接typed查询匹配；不进入正式桌面/商业阶段。

- 独立版本化提示词和严格镜头/主体/部件输出；模型只引用已注册帧，源时钟由程序推导。保留已有v1请求/hash及V1–V6基础视觉合同。
- 每个attempt保存完整ProviderResult身份、usage、费用状态、耗时、错误与typed载荷。未知费用保持null；失败/取消/中断不自动重发。
- 成功attempt写入后、发布前中断可本地恢复；同key写锁、项目预算锁、planned/ledger去重，预留落盘中断不能绕过预算。
- 离线transport fixture覆盖严格schema、不同主体/镜头、时钟、输入完整性、取消/失败、重启恢复及预算。完整verify后记录证据、提交并按已有授权推送当前分支。

## 实现与验证节点

2026-10-06（跨日接续）已实现独立actor-detail-refinement-v2提示词/HTTP适配器；v1 canonical/hash及基础deepseek_vision文件未改。复用既有bounded JPEG/JSON/usage primitives，不复用基础视觉提示词或事件parser。模型响应仅传帧ID，程序推导每个支持区间。

attempt-v2保存完整InvocationMetadata、usage、状态/错误、promptHash及typed payload/hash；取消/失败/未知费用保持null，无内部重试。planned记录含预算归属，写planned后账本失败仍占额度；同key锁覆盖send/settle/publish，项目锁保护预算。成功响应的恢复只修复账本/发布，不重发HTTP；失败记录要求显式retry。旧published侧车仍只读可用，旧无typed载荷attempt不伪造恢复。

- init完整工具链检查通过；Ruff check和mypy56 source files通过。
- 第一轮定向143通过；追加完整取消传播/损坏记录/Completed准入及现有UI回归后，**167 passed，15.00s**。
- 测试为transport fixture，无真实HTTP；覆盖未知费用、网络失败、恢复各写入边界、重复/越界/跨镜头帧、主体隔离、同图动作拒绝、外部cancel持久化后传播、schema降级/重复键拒绝。
- 即将运行完整scripts/verify.ps1（含离线重复wheel），最新完整结果仍是基线999/1skip，不能提前宣称本轮完整通过。

待完成：全量验证与证据/交接同步；本切片未接CLI/UI付费动作或typed查询manifest，检查视图默认v1身份保持原合同，v2调用显式选择identity。下一切片将接typed查询和精分析profile选择。

无新付费API；旧漫画未知预留¥4.065536及总承诺¥4.29637520保留。F006/F009/F010=false；结构fixture不作为真实精分析或独立人评。
