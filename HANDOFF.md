# HANDOFF（覆盖快照）

## 最近一次会话（2026-11-07，已恢复开发）

goal active，用户已恢复并要求持续工作。root仍在策划/转场工作分支。最新：原失败snapshot单项1通过；manifest publication最后replace已复用existing retry_file_sharing，真实跨进程占用释放/不释放及相关46项通过，独立审查通过；13508c5已推送。新完整verify session90488正在运行，日志.cache/manifest-full-verify.log，别重复启动或修改root源码。音频树33项播放/graph/DSP过，补PCM与helper隔离中；素材审查发现video_late取景头部无图像时取消终点边界P2，原owner在子树修复。先读STATUS及迭代合同。

## 主树所在分支与完整门禁

root当前codex/paused-j1-dynamic-preview-20261105，功能检查点03ac1e0已推送，尚未合main。main仍是13af6e1的已验证R3版本。动态策划/双槽dissolve组合58通过；此前受影响1174通过/2跳过。原组合3失败已修：测试editor-ready等待、安全高端口、FFT关闭历史平滑而不降低阈值。独立评估闭环采用期间编辑/项目ABA丢状态P1，以及非法三重转场预览P2。未知clock拒精确预览；fake模型不算AI质量验收。

完整verify：4871 passed/7 skipped/1 error，1449.39秒，session28158已退出1。格式/lint/mypy201源通过；本轮CLI未执行（pytest失败已中止脚本）。.cache/resume-full-verify.log。唯一错误test_saved_detail_retrieval.py::test_tampered_saved_detail_manifest_is_refused_at_read[snapshot]的fixture：test_project_detail_query.py154→ffmpeg_media.py350 write_manifest→Path.replace，media-manifest.tmp→json出现WinError5。根因未知，不断言临时锁。保留.cache/pytest-runs/0b39324b3d004598935787ed7e2d21d9，未清理。恢复首要：复现该单项/检查文件现场；必要修复后完整verify再合main，不能用旧4813或新4871声称全量通过。

## 本轮已实现但等待main合入

动态策划：按保存的原需求/候选准备→逐次确认→1–3动态方案或澄清→公开顺序/时长/缺口预览→幂等采用普通plan任务，不重发模型。新Studio12项真HTTP+fake模型过；采用等待期间以单调generation保护项目/编辑，独立4回归过。澄清空方案不能采用。

dissolve：整数帧输出时钟、双槽预加载、旧层不透明/新层渐入、三角源音增益；三速真实206、同源远跳及跨源连续转场，18张图对照生产导出帧误差≤12/255；真实WebAudio FFT淡入出方向过，非逐样本等价。非法转场用shownClips校验阻止播放/seek，独立1项过。旧取消槽/重播/成片音量回归保留。全音频ducking仍在下面WIP。

真实8768只测试了prepare_plan（HTTP200/8候选/无脚本异常），未确认发送；截图.cache/scratch/dynamic-planning-real-prepare.png。现有8秒方案到00:08末尾，wall9.86秒，8playing/8seeking，无waiting/error；.cache/scratch/real-preview-playback.json。仅单次观测，不宣称所有设备流畅。

## 两个独立暂停WIP（已提交推送，未集成）

1. codex/paused-audio-preview-20261106，6e8d384，.worktrees/j1-selected-ranges。8文件：audio-ducking-processor.js、audio-preview-graph.js、audio/preview/edit.js、tests/browser_http.py及2音频tests。DSP15项PCM对照FFmpeg通过（.cache/audio-ducking-pcm.xml）；图接线真实4媒体/四组合1项曾过，但hook生命周期/旁白起点/loop/seek/旧播放回归未完成。static路由尚未加，独立审查未做。graph使用相对import.meta.url，helper增加10013跳端口。每级limiter5ms，释放曲线未证等价，未交付。
2. codex/paused-material-clock-20261106，93d1818，.worktrees/j1-preview-corrections。main.js/test_studio_assets_browser.py：复用SourceClock统一seek/终点/重播/keys/time，unknown明确不精确定位可看整段，async映射建立后补定位并防seeking旧终点暂停。素材5真实barcode等+shell3过；.cache/studio-assets-clock.xml。独立guard被暂停中断，无结论，待续评再集成。

第三树creation-reasoning-core成果已集入03ac；不盲删junction。共享venv测试须env后PYTHONPATH=本树src；同树pytest串行，集成勿覆盖adopt generation/dissolve。

## 运行与保护

8768 PID5192为root工作分支后端；8767/8766/8765为旧服务。使用前核健康/身份，不重试杀被自动审批拒绝的8765进程。未停止用户可用工作台。

用户4份未跟踪设计文档未改未暂存。只用Codex task_*/harness_*，不搬Claude角色；重复gc-*源为客户端导入，不能推断触发者。原视频/证据/账本不改不删、不重付重标、不重跑钟馗。

语音免费本机，实际文本AI仍需独立确认；旧¥50分析授权不覆盖。无真实付费/Release，J1第四次人评仍not_usable，passes/质量不变。推送127.0.0.1:7890代理，不force。指标python -B scripts/status.py。
