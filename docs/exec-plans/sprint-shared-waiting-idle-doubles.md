# Sprint：共享离线 WaitingTransport／IdleRecorder

**状态（2026-10-22）：已交付并推送 f1fe0c8。** `WaitingTransport` 并入 `tests/fake_vision_transport.py`；`IdleRecorder` 抽到 `tests/fake_invocation_recorder.py`；`test_deepseek_vision`／`test_analyze` 改接线；新增合同测试。0 付费；不代选 A／B／D；不声称三缺口已清；不标 F006 true；不宣称人评／验收通过。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`codex/visual-details`
- Owned：共享测试双件、相关改接线／合同测试、本 sprint、交接顶部
- 不做：付费视觉、标 F006 true、代选 A／B／D、声称验收通过

## 白话

取消／超时测试用的「一直等着的假网络」，以及预算闸门测试用的「不许提前记账」假记录器，都收到公共测试文件里了，以后不用各写一份。

## Acceptance

- [x] WaitingTransport／IdleRecorder 共享且原用例改接线
- [x] 合同测试 + analyze／deepseek 相关套件绿
- [x] 0 DeepSeek／launcher；F006/F009/F010 仍 false
- [x] 已推送 `origin/codex/visual-details`（f1fe0c8）
