# HANDOFF（覆盖快照）

## 当前（2026-11-07，继续开发）

用户明确恢复开发，goal active，不因旧额度或旧暂停记录自行停工。分支codex/timed-overlays-20261107，P028定时文字/PNG叠加已接core→资产→HTTP→修订→Studio→真实渲染，仍待完整verify，尚未合main/交付。

## 主指标及已合main

J1第四次人评仍not_usable，passes/质量不变。策划/转场完整4874通过/7跳过；音频graph/素材source-clock完整4899通过/7跳过（.cache/audio-source-full-verify.log，旧session71506退出0）已合main。模型fixture不当作真人AI质量。无真实云/付费调用，语音仍免费本机。

## P028本批

合同docs/exec-plans/sprint-timed-overlays.md；API文档inspection-workspace-api.md、用户creation-guide.md已同步。overlays.js已从资产树复制集成，旧树副本不要覆盖root后续修复。

- domain输出整数帧[start,end)、Fraction淡化、规范化几何；最多16层/PNG8MiB/4096/16M/累计解码128MiB，文字120单行原值。永久资产artifacts/overlay-assets/uuid，原PNG保留，不进cache清理。
- revision省略继承/空items清除，逐层receipt/kind/text/预算核对；不改EDL/v4 manifest；render回执绑定完整快照。PNG输入追加在音乐和旁白之后，RGB合成在safe-area后、字幕/角标/水印前。
- Studio叠加页支持登记/上传、位置/宽度/时间/淡化/层级、保存/撤销/重开/清空。画布按横竖导出比例适配，成片模式隐藏live层。源片烘焙logo不能抠除。迟到登记用project/base/epoch双重核验；素材箱剪辑版本原来禁用打开，现已修复并真浏览器核验。
- 独立guard Sol/high三处P2已闭环：GET沿用sprite receipt hash防校验后换字节；RGB保留奇数坐标；overlayFrame相对4ULP纠正65/127/130精确帧浮点退位。此前shared text validator和apostrophe路径修复也已复核。guard未重跑pytest，核源码/XML，不冒称人评。

证据：前批55/68/54相关通过；本批guard11（.cache/overlay-guard-fixes.xml）；Studio3（overlay-studio-e2e.xml）；主树组合85（overlay-studio-integrated.xml）；素材箱重开联合9（overlay-reopen-integrated.xml）。新test_overlay_composition.py实证0.5x+2x、6帧转场共69帧、PNG/CJK输出时序与字幕/角标/水印覆盖顺序。Ruff与mypy206源已过。

受影响99文件运行在147项处遇旧benchmark_source_clock nonzero-mp4定位超时（146过/1失败，overlay-affected.xml）；同一项单跑无改源码通过（overlay-clock-recheck.xml），不能称99全绿。待完整门禁验证，不靠缩阈值掩盖。所有pytest同树串行，运行期间不改受测源码。

## 下一步及保护

P028首轮全量终态：3失败/4958通过/7跳过、1500.19秒，.cache/overlays-full-verify.log（session1472退出1）。三项是音频采样夹具过早启动、nonzero-mp4范围尚未可寻址被clamp、无CSS harness中画布反馈撑动/遮挡。root已集成settleExact与5调用点、reference恢复失败直接不可用、absolute画布；音频fixture在play后才record，不改容差。相关7项先过；更广audio/Studio/clock联合session59457运行中，待完成后完整verify。core树clock原104项过、新2项过，独立guard恢复失败闭锁P2已修待最后确认。

下一AI图层切片已在preview-corrections树实现未提交：creation_overlay_proposals.py新增版本快照/仅已有图层endFrame+fadeOutFrames提案、旧v1逐字节请求恢复；service/provider版本配对保持费用闸门。旧88、新12后端测试过。assets树前端三JS与new test已复制到preview树，联合session66060运行中(.cache/overlay-ai-ui.xml在该树)。真实模型0调用；fake HTTP语义不当人评。root先过P028门禁，再集成AI切片并独立审查，不能旧树整树覆盖root。后端子Agent两次Bad Request，parent接手；前端Sol已交文件。

用户4个未跟踪设计文档未动未暂存。3棵子树保留：core有旧未提交core副本；assets有本批新增模块/组合测试副本；preview-corrections干净可用于后续写者。共享venv/tools为junction，树env后显式PYTHONPATH核实际导入。至多3子树，一树一写者；不递归删junction。

旧8769 PID38232为上批服务；8768/8767/8766/8765亦旧。先核health/identity，新routes用新服务；不得绕过此前停止8765的自动审批拒绝。生产CSP不关闭。原视频/证据/账本不改不删，不重付重标，不重跑钟馗。无Release/真实平台写。push走127.0.0.1:7890代理，不force main。
