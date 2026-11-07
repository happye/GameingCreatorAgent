# HANDOFF（覆盖快照）

## 最近一次会话（2026-11-07，持续开发）

goal active。用户要求额度恢复后持续开发，不能因旧额度或旧暂停记录停工。root分支codex/timed-overlays-20261107已快进到1deb9fe，包含P028图层、AI图层时间提案及preview稳定性修复，本批技术已完整验证并合main，未按完整P028/P041或人评交付。原4个未跟踪用户设计文档未动未暂存。

## 已完成及证据

main仍为上批音频/素材clock完整4899过/7跳过，策划/转场此前4874/7。J1第四次人评not_usable不变，passes/质量不翻。真实云/付费0，语音仍免费本机。

P028：domain输出整数帧[start,end)、Fraction淡化、半向上几何；16层/PNG8MiB/4096/16M/累计128MiB。永久asset保原PNG/透明CJK sprite，receipt绑定源与sprite，客户端无路径。revision省略继承/空清除，EDL/v4不改；RGB叠加在safe-area后字幕/角标/水印前，PNG输入不改音乐/旁白索引。Studio上传/文字/时间/淡化/位置/宽度/层级、保存/撤销/刷新/清空/素材箱打开revision均已接，absolute输出画布随横竖比例适配。不能抠除源录像烘焙logo。

AI：create_overlay_snapshot显式绑定Chain.overlays与去重public资产，不能误认为EDL自带图层。模型只patch已有overlayId的endFrame/fadeOutFrames，v1请求逐字节恢复、新prompt/schema严格配对；v4保manifest，音频/其他层继承。UI临时预览不dirty，验证后原子apply clips+overlays再保存。原确认/费用/恢复闸门不变。合同sprint-ai-overlay-timing.md及工作台API/architecture/creation-guide已同步。fake语义不冒充真实模型质量。

P028早期55/68/54，root相关85、重开9、像素/HTTP guard11；AI旧88/新14、UI21、真实HTTP+fake transport→保存刷新→真实MP4第60帧绿色像素1、组合25过。core整套clock106过。guard已复核资产换字节/奇数像素/浮点帧、sourceclock失败闭锁、AI快照/恢复/应用和本次取消请求边界。guard未重跑测试，核源码/XML。

## 完整门禁与最新修复

首轮root .cache/overlays-full-verify.log：3失败/4958过/7跳过，1500.19秒，session1472退出1。第二轮overlays-fixed-full-verify.log：4957过/7跳过/6失败/1error，1872.31秒，session59221退出1；监控exec cell53已结束。两轮都不能称全绿。

修复已组合：
- settleExact等目标进入seekable才赋值，原2ms/总deadline/token/同URL重载闭锁；低轴settle语义不改。reference恢复失败不可重试掩盖；nonzero初始header2.022在origin2.478前无canonical映射，不当作有效用户T恢复；有效T错位仍禁用。真实clock106项过。
- absolute画布解决无CSS harness尺寸反馈与遮挡。
- useLatest成功路径仍查本次controller.abort，阻止取消body解析返回null后读runs。
- 选段onInput立即更新，避免失焦前被异步seek rerender覆盖。原范围/观察覆盖校验不变。
- 稳态ducking使用4秒非循环fixture，等三路媒体时钟>=.25后录，原阈值不变；原1秒hook循环fixture保留，避免循环相位破坏稳态谱测量。assets/planning/audio联合23过。

最终root完整组合verify已通过：.cache/overlays-combined-full-verify.log，4981 passed/7 skipped、1734.98秒，格式/Ruff/mypy207源/CLI通过；session89751退出0。先前root集成20过，import确认为root/src。代码与证据合main后继续字幕主线；没有真实云/付费、人评/feature passes不变。共有venv editable指root，子树直接verify会清PYTHONPATH误导入root，完整门禁在root执行，工具链检查不删。

## 子树与保护

下批Studio字幕已在preview树codex/studio-captions-20261107提交推送a4b6ed0：后端复用不变、本地字幕/清空/撤销/保存/重开/删除过滤/替换禁编，24项字幕及7项浏览器过（重叠不相加），guard闭环通过。原转录不改，真实SRT/MP4已测，即时预览无字幕已提示。root未跟踪合同sprint-studio-caption-editor.md与该分支同名，集成前保存到scratch避免遮挡。接下来集成字幕、相关检查及下一完整门禁；不能把未集成当已实现。

preview树当前codex/studio-captions-20261107在a4b6ed0已推；overlay-assistant分支1deb9fe为此前组合快照。无MERGE_HEAD。core保留clock修复/旧core副本，assets保留前端旧副本，勿再覆盖root。3子树、一树一写者、同树pytest串行；env后核PYTHONPATH与实际导入。root原未跟踪AI合同已移到.cache/scratch备份避免快进遮挡，用户4份文档未碰。

旧8769 PID38232及8768/8767/8766/8765均旧服务，先核health/identity；新routes用新进程，不绕过停止8765的自动审批拒绝。生产CSP保留。原视频/证据/账本不改不删、不重付重标、不重跑钟馗。无Release/真实平台写，push走127.0.0.1:7890代理，不force main。状态计数只由python -B scripts/status.py计算。
