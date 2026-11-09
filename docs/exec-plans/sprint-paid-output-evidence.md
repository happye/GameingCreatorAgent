# TD026 付费返回结果的本机留痕

2026-11-09；root唯一写者；沿用既有Astra/low设计，不新增真实付费调用。

## 范围与验收

- Provider返回COMPLETED后，在验证或编译前，用既有不可覆盖write_creation/receipt保存`attempt/provider-output/output.json`，包含独立schema、preparedHash及完整parsed output。结果仅附文件SHA，不把未验证输出直接暴露HTTP或采用。
- 应用失败保留受控`failureStage`：provider、persist_output、validate_proposal、compile_plan；不序列化异常文本、路径或模型原文。保存失败停止验证/采用，账本和已返回metadata仍保留；最终结果写失败继续传播且阻止重发。
- 结果引用须校验原文件receipt、schema、prepared身份与SHA。旧结果没有引用时按旧协议读取；历史读取不要求当前源文件仍相同。无最终结果时仅允许Python本机读取留痕，不重建成功状态、不编译、不采用、不重发。
- fake transport测试覆盖校验失败、编译失败、留痕写失败（已知/未知费用）、最终写失败、原文字节/身份/引用篡改及旧记录兼容，均检查最多一次发送。唯一Sol/high审查费用、持久化与身份边界；受影响验证后与P018批次完成一次完整门禁。

## 不可恢复的旧现场

单次许可已耗用，原preparedHash `9bcc9d01729bf0e59ff4934fdacaf5f6ed74c12147b1741c95eb0fa83bc0dcea`失败原文未保存，不能用新机制补造、回写或自动重发。账本估算¥0.05877非实扣对账；旧result/receipt不变。此修复仅防止新调用再次失去离线诊断材料，不代表真实策划质量通过。

## 验证记录

Sol/high唯一边界审查通过：独占留痕、receipt/schema/身份/hash、旧记录兼容、保存失败保账本及attempt阻止重发；未执行外部调用。root的evidence/service/HTTP/plan jobs组合60项通过，15.444秒；`test-affected.ps1 -Browser -PytestArgs '-k reasoning'`为82通过、454 deselected，68.04秒。证据`.cache/paid-evidence-affected.xml`和`.cache/paid-evidence-script-affected.xml`。Ruff及两处源文件mypy通过。本批完整门禁待执行，不宣称真实模型质量验收。

## 用户纠正后的暂停记录（2026-11-09）

本次全量首次5108过7跳3失败，2229.875秒；失败范围仅音频采样测试及级联清理，修复后整文件10项连续三轮通过，业务音频代码未改。第二轮全量属于不必要扩大，按用户要求在约92%停止，记录`.cache/knowledge-evidence-hook-fixed-full-stopped.json`，不作全量绿。复用已通过业务证据和定向修复结果，不为“闭环”自动重跑；后续全量放到下一实质业务批次。当前保存开发分支，未集成main或提高人评状态。完整规则已写入根AGENTS.md Testing。
