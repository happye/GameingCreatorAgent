# F002：本地媒体与源时间映射

日期：2026-10-03。Owner Codex /root；分支 `codex/F002-media`；前提 F001/main `754125f`。根 Agent 编写媒体服务/测试；Windows Job helper 的两个文件分配给 `f002_windows_job`，在 `.worktrees/f002-job` 的 `codex/F002-job` 独立编码，root 串行集成。其他专业 Agent 只读设计/审查。

## 计划与验收

实现独立媒体 service、整数 PTS/有理数时基 DTO、隐藏且可取消/超时的进程调用、抽图和 16k 单声道 WAV，以及核验后发布的本地 manifest。不提前将 analyze 改为虚假完成，不引入模型或数据库依赖。

规范化 origin 取选中音视频流最早有效 presentation start，保存精确 Fraction；微秒点/起点向下取整、结束/时长向上取整。图片按原始 PTS 映射；音频保存每个输出帧的 WAV sample offset、PTS、sample count，显式识别 gap/overlap，不用单偏移替代分段映射。

验收：真实四段素材与合成 CFR/VFR/nonzero PTS、音轨偏移和无音轨；纯 DTO 另验 negative PTS；坏文件、来源变化、日志/文件不一致、取消/超时/大量 stderr；源映射和产物 hash 可追溯。测试不联网、不付费；未核验输出没有完成 manifest。

## 验收结果

F002 已通过。`./scripts/verify.ps1`：87 tests passed / 10.73s，0 skipped，warnings-as-errors；Ruff 27 文件、严格 mypy 21 文件、静态导入方向均通过。两个离线 wheel 相同 SHA256：`977e179fde1042b19628d907e5dcabd08b713724ac9a771b68518fea35f9bbf9`。

`./scripts/test-media.ps1 -AllLocal` 使用已固定本地 FFmpeg，四段完整预处理成功。最后报告 `artifacts/media-F002/026b702c0d8d4a65ba29c744bcf15140/validation.json`（忽略文件）；不发送模型请求。

| 素材 | 规范化时长（µs） | 图片 | WAV 样本 | 音频不连续点 | 本次观察裁除样本 | 处理秒 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Atom PV | 64,943,220 | 65 | 1,038,933 | 0 | 562 | 1.719 |
| Atom 实机剪辑 | 54,743,220 | 55 | 875,733 | 0 | 665 | 1.616 |
| Atom 2025-08-17 录像 | 275,831,000 | 276 | 4,413,093 | 12,928 | 6 | 10.125 |
| 漫画群星 PV | 95,175,874 | 96 | 1,522,667 | 0 | 546 | 2.409 |

合计 490.693314s 素材、492 张图片，顺序预处理约15.869s。时长 ceil 的1µs差异不改写 F000 历史 float 记录。此速度只含本地媒体处理、短素材及当前机器缓存，不是 ASR/Vision/检索端到端或小时级结论。

## 验证与修复证据

- 14 个时间/解析测试：精确 Fraction、VFR、正负原始 PTS、共同 origin、音频 gap/overlap、边界量化、日志顺序和末次 hash 取消。
- 9 个媒体集成测试：CFR/VFR/nonzero、先/后音轨、无音轨、时间戳 gap、坏文件、采样上限、源变动、阶段/最终发布取消。
- 5 个进程与 9 个 Windows Job 测试：启动前/后取消、超时、超限仍 drain、双管道、无限 stderr、venv redirector/后代回收、故障清理与句柄释放。
- 修复实测 AAC 尾部越声明时长：按音轨 end_pts 明确 atrim；首样本量化可在 origin 前不到一输出样本，保留裁切量及不确定性。
- Windows 只杀父进程会遗留真实解释器。worker 独立 worktree 实现挂起启动→Job→恢复；root 集成后发现 Job 关闭是异步，必须等后代 pipe EOF 才结束读任务。严格警告测试现通过。
- 两位只读审查者都指出最终 hash EOF 取消竞态；补 EOF 和发布前 check，新增两个回归后接受当前范围。
- `init.ps1` 精确 Python/FFmpeg 九个二进制/DLL hash 校验通过。用户/系统环境和三处 Python 注册表指纹仍与安装前一致。

## 限制与接续

支持范围与 TD001–TD003 见 `docs/references/media-processing.md`、tech-debt。16MiB stderr 暂不支持任意长素材；无精确 stream 元信息明确拒绝；只验证选中帧单调；裁除计数仅统计本次实际请求到的 decoded frame。

F003 消费 sample-piece 映射，禁止 WAV 秒数直接当源时间。F004 持久化 namespace/evidence/hash 与恢复，文件 bundle 完成不等于 AnalysisRun 完成。应用 analyze/search/benchmark 仍 stub；F003–F006、人工 U10 gate 保持未验收。
