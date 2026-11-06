# HANDOFF（覆盖快照）

## 最近一次会话（2026-11-07，持续开发）

goal active，用户要求持续开发。音频graph/素材clock批次完整verify4899 passed/7 skipped、1179.88秒，格式/lint/mypy201源及CLI通过；.cache/audio-source-full-verify.log，session71506已退出0，合入main。源状态无需重复全量。实际8769四路graph running/gate1，旧8秒方案到末尾无pageerror/alert，.cache/scratch/audio-real-preview.json/png；保持CSP，字符串wait_for_function会unsafe-eval报错，用locator等待/CDP函数体读。无真实付费。下一批P028见下面新增段。

## 已合main

策划/转场4874/7、音频/素材clock4899/7完整门禁过，详细证据见迭代合同。J1第四次人评仍not_usable，passes/质量不变；真人AI质量未验。

## 已集成两树

音频082b1be与素材7f50700已合入本批，生产static两路由已注册。原子树36+独立Studio1及素材9+独立video_late1的结果不冒充组合；root后来组合46、完整4899/7均过。真实Studio fixture中planner/SAPI/SQLite timeline/runs是假，解码/probe/hash/回执/HTTP/播放器/PCM是真。每级limiter5ms，释放曲线未证与FFmpeg等价。主树已更新，不再重复取这些旧树文件覆盖新开发。

## 运行与保护

8768 PID5192曾是本策划分支服务；8767/8766/8765旧后端。使用前核健康/identity，后台进程可能尚未加载新routes；不得绕过此前对停止8765的自动审批拒绝。

用户4个未跟踪设计文档未动未暂存。共享venv/tools为junction，树内env后PYTHONPATH须本树src；affected脚本会重设，按同清单直接pytest并记录差异。并发≤3树/一写者每树。同树pytest不重叠。

原视频/证据/账本不改不删，不重付重标，不重跑钟馗。无真实云/Release。status数字python -B scripts/status.py，质量不由开发测试代填。push走127.0.0.1:7890代理，不force。

## 下一批P028（未交付）

输出时间线的定时文字/PNG独立层：startFrame/endFrame左闭右开，x/y/width归一化0..10000，淡入/出frame，层序固定。不能编辑烘焙源logo。root合main后建新feature分支。

协议worker timed_overlay_core在.worktrees/creation-reasoning-core已写domain/creation_overlays.py和tests/test_creation_overlays.py，25focused/ruff/mypy过，未提交。top schemaVersion=creation-overlays-v1/items；每item overlayId/kind/startFrame/endFrame/x/y/width/fadeInFrames/fadeOutFrames/assetId/assetReceiptSha256，text额外rawtext。Opacity Fraction，几何半向上等比，超画布拒绝，预算16层/PNG8MiB/4096/16M/累计128MiB（同资产计一次）。三速仅纯输出frame测试不冒称render。

资产worker overlay_assets在.worktrees/j1-selected-ranges branchcodex/timed-overlay-assets-20261107做新infra/overlay_assets.py及test（可拆overlay_text.py）。接口OverlayAssetLibrary(repo)，async register_png/register_text，resolve(id,receipt)；public assetReceiptSha256、width/height、kind text/image、text仅text，无路径。永久artifacts/overlay-assets，原PNG不删；真实FFmpeg ASS alpha=1/MicrosoftYaHei透明CJK proof已成功，注册/预算/receipt测试仍在跑。不要覆盖该树正在写的文件。

后续还须资产/文字身份验证、metadata省略继承/显式空清除及旧v4兼容、输出帧叠加render（safe-area后字幕/徽标/水印前）、Studio上传编辑/版本重开/预览/导出真实闭环及独立quality guard。当前仅组件，不能翻P028状态。