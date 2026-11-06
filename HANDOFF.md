# HANDOFF（覆盖快照）

## 最近一次会话（2026-11-07，持续开发）

goal active，持续工作。root现codex/audio-source-clock-integration-20261107，42c0c40已推送：已合音频082b1be/素材7f50700并加生产static两路由，组合46通过（.cache/audio-source-combined.xml）。新完整verify session71506正在跑，.cache/audio-source-full-verify.log；勿重复启动/改root源码。main已2878004且4874/7完整通过。真实付费仍逐次独立确认，语音免费本机，不搬Claude角色。

## 已验证并合入main的批次

策划/双槽预加载+dissolve、UI采用竞态保护、manifest有界sharing等待。最新完整verify 4874 passed/7 skipped，1124.26秒；格式/lint/mypy201源、CLI均过。.cache/manifest-full-verify.log，session90488已退出0。此前4871/7/1 error不是绿：原snapshot fixture Path.replace WinError5具体成因未证实，单项重跑过，随后只包最后replace的retry_file_sharing（1s后仍抛原异常）并用真实跨进程释放/持续占用验证；46相关过，独立审查过。没有重跑paid或生成证据流程。

动态策划prepare_plan从保存原需求/候选快照，逐次确认一次send，1–3案或澄清、时长/缺口预览、幂等采用普通plan不再send；12Studio浏览器过，采用期间编辑/项目ABA保护独立4过。文本模型均fake，不能叫真实AI创作质量通过。

dissolve：整数frame输出时钟，双槽原片预加载，旧层不透明/新层渐入和三角源gain；3速真实206、同源远跳和跨源连续转场，18张图对照导出误差≤12/255，FFT方向过。非法shownClips三重布局明确挡播放/seek。root组合58通过。全音轨ducking见下一批，J1第四次人评仍not_usable，passes不变。

## 下一批待集成（两树成果已推送）

1. 音频codex/paused-audio-preview-20261106，082b1be，.worktrees/j1-selected-ranges。生产6e8d384含processor/graph及audio/preview/edit接线；后续tests/helper已082b1be。DSP15实际PCM对照FFmpeg误差<1e-5；36组合（15DSP+2graph/hook+2keygain+16旧播放+helper1）过，.cache/audio-lifecycle-final.xml。另新增真实Studio1项过.cache/studio-audio-vertical.xml，必等末尾重播，确认00:00/源6秒起点+PCM有声，再暂停静音/退出contextclosed。fake仅planner/SAPI/SQLite timeline读取/runs响应；实际probe/hash/MusicLibrary/HTTP/保存回执/PlanPlayback/解码PCM真。独立源码及证据审查过；36+1尚未合37项跑。PCM相位容差120ms，不冒称全部速率/所有跨源全流程。每级limiter5ms延迟，释放曲线未证与FFmpeg等价。
   必须父控server ASSETS加/assets/studio/audio-preview-graph.js和audio-ducking-processor.js；测试临时注册不等于生产已注册。合入要保adopt generation/dissolve，不整文件覆盖。helper禁Windows reuse且10013/10048跳端口，同树pytest严格串行。
2. 素材clock codex/paused-material-clock-20261106，7f50700，.worktrees/j1-preview-corrections。main.js/test_studio_assets_browser.py复用SourceClock统一seek/keys/终点/replay/time；unknown明确不精确定位可看整片。新P2：video_late[0,1]取景含无图像头部曾取消边界，已改合法canonical端点始终安装end约束，选段/replay从首画面.5起但原range不变；全片快捷键保音频头部0行为。6browser+shell3=9通过，独立新增真实video_late1通过，.cache/studio-assets-clock-resume.xml。尚未主树集成/全量。

已建集成分支/合两批/加static并组合46通过；下一步跟踪session71506完整验证，成功后才merge main并更新API/架构/STATUS。第三creation-reasoning-core成果已在main，不盲删树/junction。

## 运行与保护

8768 PID5192曾是本策划分支服务；8767/8766/8765旧后端。使用前核健康/identity，后台进程可能尚未加载新routes；不得绕过此前对停止8765的自动审批拒绝。

用户4个未跟踪设计文档未动未暂存。共享venv/tools为junction，树内env后PYTHONPATH须本树src；affected脚本会重设，按同清单直接pytest并记录差异。并发≤3树/一写者每树。同树pytest不重叠。

原视频/证据/账本不改不删，不重付重标，不重跑钟馗。无真实云/Release。status数字python -B scripts/status.py，质量不由开发测试代填。push走127.0.0.1:7890代理，不force。
