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

## 当前P028（未交付）

root在codex/timed-overlays-20261107。core/assets/HTTP已主树相关55通过（.cache/overlays-http.xml），格式/lint/mypy205源通过；版本链已接入（相关68过），未做P028全量、Studio尚未接，不翻交付/质量状态。子Agent额度限制，parent当前接手；不要重复派任务假称已执行。

新增domain/creation_overlays.py：top schemaVersion=creation-overlays-v1/items；item overlayId/kind/startFrame/endFrame/x/y/width/fadeInFrames/fadeOutFrames/assetId/assetReceiptSha256，text另有rawtext。26core过。公开validate_overlay_text原值不trim，禁止{}\<>/category C/单行，assets登记/resolve复用，guard文字差异P2已修。纯输出frame Fraction fade、半向上几何、16层/PNG8MiB/4096/16M/累计128MiB去重。不能修改烘焙源logo。

新增infra/overlay_assets.py永久artifacts/overlay-assets/uuid，原PNG不删；真实FFmpeg ASS alpha=1/微软雅黑透明120字CJK证明，DTO无path，public assetReceiptSha256。guard第二P2路径含apostrophe无法渲染已由parent修：新ffmpeg_filters.filter_path提取原ffmpeg_render._filter_path逻辑，旧私有函数保一行兼容转发，asset复用shared escaping不额外quote；含Creator's repo中文sprite回归过。原guard额度耗尽后未复核最终两个修法，不可写独立闭环已通过。

新增ui/overlay_jobs.py：register_asset严格text/image请求，resolve_assets核kind/text/receipt与解码预算。POST /api/creation/overlay-assets text{kind,text}或image{kind,fileName,dataBase64}；GET /api/creation/overlay-assets/<id>/image?receipt=<sha>走VerifiedMediaCache；server只该upload放宽11MiB body，rawPNG≤8MiB。HTTP真上传/读取字节/Origin/query/未知字段/base64/借用别的text拒绝过，无模型调用。

metadata现已支持省略继承/显式空清除及旧v4兼容，按当前输出frames验证范围，editor提供overlays及overlayAssets公开URL/尺寸；相关68通过（.cache/overlays-version-chain.xml），新3回归保存继承清除/重启/剪短拒绝/篡改拒绝。render_revision现已传递overlays给真正FFmpeg合成（safe-area后字幕/徽标/水印前，追加PNG输入不可改音乐/旁白索引）；渲染已实测2种有/无BGM、两层覆盖、首末帧/淡化/几何/20帧总长，首轮发现浮点setpts重帧已改叠加路径settb=1/fps,setpts=N（旧无叠加路径不变）。实际保存revision→正常render job→MP4→任务重开也通过，回执核overlay快照；相关54通过.cache/overlays-render-integrated.xml，ruff/mypy206源通过。下一步Studio上传编辑/版本重开/输出时钟preview，并补中文/字幕/水印、变速/转场等组合的像素及UI验证。需要最终identity/persistence独立guard，子Agent额度恢复后再评估。core/asset旧子树有副本但不再覆盖root修法。用户4个未跟踪设计文档不动。
