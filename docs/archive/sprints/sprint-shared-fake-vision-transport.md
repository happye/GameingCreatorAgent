# Sprint：共享离线 FakeVisionTransport

**状态（2026-10-22）：已交付并推送 9e62ae9。** 抽出 `tests/fake_vision_transport.py`（队列／重复回复／before_post／`offline_chat_completion`），`test_analyze`／`test_deepseek_vision`／`test_temporal_*` 改用共享双件。0 付费；不代选 A／B／D；不声称三缺口已清；不改 feature_list。

## Assignment

- Owner：root／GamingCreatorAgent
- Branch：`codex/visual-details`
- Owned：`tests/fake_vision_transport.py`、相关测试改接线、本 sprint、交接顶部
- 不做：付费视觉、标 F006 true、代选 A／B／D

## 白话

四个地方以前各写了一份「假的网络发送器」。现在收成一份共用的离线假发送器，测试更整齐，也保证不会真的上网。

## Acceptance

- [x] 共享 FakeVisionTransport／offline_chat_completion
- [x] 四套原测试改接线且绿；新增合同测试
- [x] 0 DeepSeek／launcher；F006/F009/F010 仍 false
- [x] 已推送 `origin/codex/visual-details`（9e62ae9）
