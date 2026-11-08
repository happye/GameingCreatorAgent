# Studio 本机旁白修订与真实制作收口

2026-11-08，自主恢复后接收 Grok 第二轮已有成果；不是整项 P018/P020 或创作质量验收。

## 合同与边界

沿用现有任务、修订、免费本机语音、FFmpeg 和发布包 API。用户修改挂接旁白后可重新合成并保存新版本；失败或等待期间编辑状态发生变化时保留当前音轨。新旧修订可分别回读，旧证据不改。真实云端、付费语音和平台发布均不执行。

唯一 task_quality_guard（Sol/high）完成知识费用/快照/引用审查，未发现知识路径阻塞；同轮发现重合成期间撤销/裁剪可被迟到结果覆盖。修复以 clips/audio 编辑代次隔离返回，包含 ABA；该修复经同一审查者定向复核通过，未叠普通审查。

## 当前证据

- `tests/test_studio_narration_revision_browser.py`：3 passed，16.42 秒。延迟真实 POST 返回期间撤销，结果保留当前音轨；成功路径保存新修订后，新旧 asset 不同、位置 30 帧、gain -6、混音保持且旧编辑结果不变。日志 `.cache/studio-resume-revision-final2.log`，XML `.cache/studio-resume-revision.xml`。
- 独立真实媒体流程：`.cache/scratch/resume-real-media.py`，日志 `.cache/studio-resume-real-media2.log`，结构化结果 `.cache/scratch/resume-real-media/result.json`。复用已有 service/saved_plan，但恢复真实 `execute_render_creation`；真实 FFmpeg 渲染和包编码均未 mock。仅本机语音引擎以明确 fake 生成两条 2 秒 WAV（440/880Hz），时间线库使用既有隔离 fixture。
- 隔离仓库 `cb8f3c15b61c45178b94302902e05b3b`：静音合成源，6 秒真实普通方案；旧/新语音经真实任务回执和两次修订挂接，start 30 帧、gain -6、ducking off、无 BGM。旧修订目录所有原文件逐字节保持。
- 新修订真实 MP4：render `ecf58f6a92294755bf230b34dd1c9483`；回执 180 帧、30fps，ffprobe 180 帧、30/1、6 秒。解码后 1.25–1.75 秒窗口，880Hz 幅度 0.24470486、440Hz 幅度 0.0000002475；满足 >0.01 及 >5 倍条件。
- 同一 render 经真实 publication → B站 profile → package `e9e501e4b35d4031820e368ba8e124a8`；ZIP 七文件集合与现有 FILES 完全相同。localChecks pass，publicationEligibility unverified；平台规则、来源权利和人评保持 unknown，不代表可真实投稿。
- 完整门禁正在运行：`.cache/studio-resume-full-verify.log`、session 27435。源码冻结清单 `.cache/studio-resume-source-freeze.json`。原受影响组合为修复审查发现而主动中断，不作通过证据。

## 仍未证明

同一隔离仓库内规则 → 知识动态策划 → 采用 → 旁白 → 成片的 R39–R44 全链尚未贯通；本轮真实媒体证据覆盖 R42–R44 的任务/媒体路径，不冒充完整 Studio 操作验收。R09、旧 v1 磁盘夹具、跨 scope 专项、双尺寸专项等剩余项以原工单及 R48 报告为准。无真实声音质量、模型内容质量或人评提升。

## 同库任务链补证（随后完成）

`.cache/scratch/resume-full-journey.py`，最终退出 0，日志 `.cache/studio-resume-full-journey-final.log`；`summary.json`、`planning-evidence.json` 和 `result.json` 位于 `.cache/scratch/resume-full-journey/`。脚本 SHA256 `873713016ce30e5e9cfbe4d18ab49a1a858ba3b2807201dbeb4522f13aa4f417`。

同一隔离仓库 `5dae1aeb341b43b6a042ddc7bf45117b` 经真实规则 HTTP 提取 `#fact#` → 填入普通计划 Brief → 真实知识 HTTP 登记 → 动态 prepare；确认前发送 0 次。明确 fake 文本传输返回合法 v2，实际 user 请求逐字等于报价预览，确认/采用/重复采用后总发送 1 次，重读的采用结果含该知识 entryId。随后沿真实旁白任务、两版修订、MP4、publication、B站七文件 ZIP；新 render `ef4cab27e7a2418087e9d816fdf0d3b2`，package `252efe3441dc40358274def8c9230e85`。再次验证 180 帧、30fps、6 秒及相同信号幅度条件；旧修订目录字节保持。localChecks pass，投稿资格仍 unverified。

这补齐 R39/R40 与 R42–R44 的同库任务/媒体路径，仍不等于全部 Studio 点击操作通过。R41 调用了真实 narration-script，但该 6 秒方案预算仅 18 字，已有模板内容占用后 citations 为空，故本例**未证明旁白知识引用展示**；不降低生产字数预算或伪造 citation。先前“未贯通”描述是补证前状态，以本节为最新证据。真实 AI/语音质量、人评和平台发布仍未验。

## 草稿资产隔离最终修复

补查发现撤销从新asset B回旧asset A时旧编辑器可把B稿写入A键。清理scope effect增加attachedAssetJobId依赖，切轨关闭编辑器并使旧会话失效，重新打开按当前asset恢复。唯一Sol/high定向复核通过；4 passed /20.79s（.cache/studio-resume-revision-scope.log/XML），Ruff/format通过。本轮审查范围现已闭环。原完整verify在63%主动中止用于修此实际缺陷，未发现失败但不是通过证据；日志保留。最终全量改用.cache/studio-resume-final-verify.log，源码清单用.cache/studio-resume-final-freeze.json，前序证据不覆盖。
