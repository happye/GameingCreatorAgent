# HANDOFF（覆盖快照）

## 最近一次会话（2026-11-07，额度恢复持续开发）

用户目标：按计划持续开发直到额度用光；goal active，不能自行停工/缩成小目标。root分支codex/timed-overlays-20261107，main以git refs为准。4个用户未跟踪设计文档未动未暂存，禁止git add全目录。不要复制Claude/Cloud角色到Codex；此前重复来自客户端external_agent_config_imports，不是模型提示词。

## main与验收

P028文字/PNG与AI图层时间提案f08d0e5：完整4981/7跳、1734.98秒，.cache/overlays-combined-full-verify.log。Studio逐镜字幕e98e913：完整4986/7跳、1782.19秒，.cache/studio-captions-full-verify.log，格式/Ruff/mypy207源/CLI过。原转录不改。不能抠除源视频烘焙logo，真实AI语义/创意/真人观感未验收。

status.py最近实算51=10交付41部分，质量0/51，F8/3，债25=17解决3部分5未解，人工9。J1第四次not_usable，J2/J3未做人评，技术绿不能翻passes/质量。本机免费语音，无真实云/付费/Release/实际平台发布。

## root运行时身份集成（未提交merge）

来自已推codex/workspace-runtime-identity-20261107的711734f，runtime guard通过；本批root完整门禁已绿，准备提交当前merge并FF推main。提交后MERGE_HEAD应消失，以git refs为准。

首轮session97268退出1：仅旧health整对象断言漏runtimeIdentity，1失败/4999通过/7跳。补当前包根/hash后相关42过/1跳57.241秒，.cache/runtime-health-contract.xml。最终session99097退出0：5000过/7跳1716.69秒，.cache/workspace-runtime-fixed-full-verify.log，格式/Ruff/mypy208源/CLI全过。失败日志保留，不冒充第一轮即绿。

stdlib包源码指纹在服务启动固定，health返回packageRoot/version/hash；PS独立dev/portable来源、显式PYTHONPATH，拒旧进程复用并提示新端口，保留原PID/repo/owned helper检查。NTFS junction剪枝/读前包内校验已修。真实root临时8770 PID28620启动+复用、health与源码匹配、Studio及模块200，.cache/runtime-live-smoke.json；测试后只清理本次28620，旧8765–8769未动。新端口8770目前无本次服务。

## 字幕预览已在功能分支，待root完整集成

preview树分支codex/studio-caption-preview-20261107，已推2c89477，树干净；基线fc90e85已含711734f及e98e913。Sol/medium caption_preview_impl完成，唯一Sol/high caption_preview_guard专项通过，无遗留缺陷。

只读POST共享修订/转录/SRT毫秒及ASS百分秒/lifted；UI outUs+250ms/abort/seq/key清旧。guard发现旁白依赖jobs.get恢复写盘P2，现read_only贯穿load_chain/resolve/asset，非completed拒绝，正常默认恢复保持。后端111过0跳70.651秒(.cache/caption-preview-backend-final.xml)，浏览器12过0跳54.266秒(.cache/caption-preview-browser-combined.xml)。同v4B run/2x/3帧双字幕草稿真实SRT/ASS/MP4；迟到success/error跨project/parent/none、重复A/A/B、继承删除/字段注入/依赖全字节不变均覆盖。Ruff/format/mypy5源过。

合同/架构/API/指南/feature evidence已随2c89477，未翻状态。root有parent未跟踪同名sprint-studio-caption-preview.md旧稿，merge前移动到.cache/scratch备份以免冲突；应采用分支最终稿。不以定向绿代完整gate。

## 正在独立实施P035多平台批量包

Sol/medium /root/multi_platform_impl唯一写assets树.worktrees/j1-selected-ranges，分支codex/studio-multi-platform-20261107基于e98e913。合同root sprint-studio-multi-platform-packages.md；Astra选pub投影+UI串行，无batchmanifest。Sol/high multi_platform_guard发现3P2，串行及跨project旧open已修；未知retry尚未注册时重复requestId窗口正在补scoped sessionStorage意图，恢复后不可遗忘未知R。真实双七文件ZIP/解码、105历史、Free、失败重试及迟到已有证据；最后修复需同guard复核，未提交/集成。不要重复派普通review。

该树旧tracked/untracked源改动完整保存在stash b55207b68ce12b3682607687c54dc818d1f6f849，禁止drop/pop覆盖新实现。core树仍保留旧clock副本，不整树覆盖root。≤3子树，一树一写者，同树pytest串行；共享venv editable指root，env清PYTHONPATH，子树必须env后显式设自身src并核import，完整verify在root。

## 操作红线

不绕过既有停止8765审批拒绝；旧服务均先核health/PID，改磁盘不代表已重载。原录像/分析证据/账本不改不删、不重付重标、不重跑钟馗。push用127.0.0.1:7890代理，禁止force main。
