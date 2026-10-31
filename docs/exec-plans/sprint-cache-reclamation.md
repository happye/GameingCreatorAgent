# 严重缓存事故：58.29 GiB测试中间文件（2026-10-31）

用户报告项目缓存突然增加50多GB、重复项目目录及备份，要求子代理清理、自动回收和完整根因证据链。此问题优先处理，Goal仍active；本地旁白实现继续保留，尚未交付，不计P026。

## 已确认事实

- 原`.cache`可读部分75,781,988,883字节，worktrees为64,183,447,406；clip-speed-render内部.cache为62,619,546,236。全量只读scandir结果`.cache/cache-size-audit.json`，含无法读取项，未跟随reparse。
- 单文件`.cache/worktrees/clip-speed-render/.cache/late-tests/test_clip_before_audio_stream_0/late/part-000000.nut`为62,589,501,440字节（58.29GiB），本地时间04:10:16.061创建、04:10:42.289最后写入。不是把所有项目副本体积推断成58GB；绝大多数新增空间可定位到此单文件。
- 用户明确授权删除无用缓存；主控只批准该精确单文件。Astra/low cache_reclamation子代理核对ResolvedPath、全部父无reparse、无pytest/FFmpeg、Windows独占打开后，原生PowerShell单文件删除。G free从49,950,846,976到112,540,352,512字节，实测释放62,589,505,536字节。审计`.cache/cache-single-file-reclamation.json`含大小/时间/前256字节摘要，不为计算SHA重新读58GB。

## 生成与遗留的证据链

1. `tests/test_clip_speed_render.py`的`test_clip_before_audio_stream_is_exact_silence`生成64×48/20fps/4秒红色测试视频，音频从3秒开始，裁取0–2秒，以0.5x/2x渲染；仅设置CancellationContext 60秒。
2. 实际Codex原会话`rollout-2026-10-31T04-04-35-01a18e6a-06ef-7271-9e00-b2c46a1e47bd.jsonl`第135/149行记录`pytest ... -k before_audio --basetemp=.cache/late-tests`；04:10:42第148行记录给session70895发送Ctrl-C，随后增加“源区间与音轨无交集则audio=None/anullsrc”的修复并改在`.cache/late-fixed`重跑。文件最后写入时间与中断相符。精简提取`.cache/cache-root-cause-session-evidence.json`。
3. 当时空音频参与tempo/padding的缺陷导致未按预期有限终止。当前代码已有无交集静音分支；最终19项回归XML（clip-speed-render树.cache/speed-concat-final.xml）04:18记录两种速率分别约0.876/0.857秒通过。修复功能没有同时清理旧失败目录。
4. 媒体进程原只限制stdout/stderr及执行时间，没有输出文件字节/渲染临时总量限制。26秒足以写58GiB，60秒超时无法保护磁盘。测试没有结束回收；切新basetemp绕开旧文件，`.cache`被.gitignore隐藏，旧工作树又长期保留。

## 哪条规则要求什么

`AGENTS.md`第52行要求并行写者独立worktree；`docs/references/agent-workflow.md`第83行更宽地要求每个编码Agent独立分支/worktree。这些解释了重复的项目目录结构。Harness技能SKILL.md第96附近只要求结构化交接/按需隔离，第123行的backup指子Agent配置增量修改的回滚备份，未要求无限保留项目副本或失败的大媒体。

长期保留已集成工作树/全量失败输出，以及将活跃未提交源码放入名为cache的目录，是执行和生命周期设计缺口。隔离并行写入的目的仍合理；不应以该规则为长期堆积开脱。源码副本占用须另测，不把副本数量等同58GB；复制本身不代表模型token消耗，后续重复初始化/读取/扫描造成的工作成本亦需避免。

## 已实现并验证的保护

- 主控`MediaOutputLimit`：原生FFmpeg `-fs`硬限制，进程50ms监测文件/私有目录总量/磁盘余量，退出时仍检查，达到限额不能把FFmpeg零退出误判成功，回收超限输出。
- 渲染中间文件按已验证帧数/尺寸计算容量，最低8MiB、最高2GiB，单次私有渲染目录4GiB，磁盘保留2GiB。失败/取消路径回收确定性NUT/清单，不删除原素材或已完成MP4。
- `tests/conftest.py`只读取已使用的tmp_path，在fixture teardown后回收可再生媒体，不给全部测试强制造临时目录。`scripts/cache-maintenance.py`严格限定实际fixture根、拒绝链接/工作树/模型/workspace；失败保留小信息与前缀摘要。手动`reclaim-cache.ps1`默认干跑、明确文件、24小时与进程/锁保护。
- 工作树生命周期和目录布局规则已在AGENTS/agent-workflow明确：只在并行写确有需要时隔离；活跃源码不能放.cache；已合并副本确认恢复依据后释放，避免无限留备份。

初轮13项通过。扩展媒体进程/变速/转场/混音`.cache/cache-fix-main.xml`为58通过/3失败，三失败均为旧mock未接受新增output_limit关键字；保留原XML，修正mock并转发真实参数后，三项加8回收边界及新渲染容量失败回收共12项通过（`.cache/cache-fix-incremental.xml`）。包括真实无限anullsrc+FFmpeg -fs零退出仍触发限额，以及2KiB低预算渲染失败后NUT清空/原素材及BGM SHA不变；5源码mypy/Ruff与格式检查通过。cache_safety_review Astra/low只读限定PASS，未重复运行/删除，不代替主控实际证据。

## 另一个尚未归因的事实

活动`.cache/worktrees/narration-integration`已消失，Git登记prunable；用户明确说没有手动删除，清理子代理执行记录仅只读扫描，未删任何目录（后来只获准删上述单文件）。没有证据就不能归因给用户、清理子代理、Harness或杀毒。Windows Defender可读日志未见相关事件；原因未证实。此前旁白新源码可从本对话工具补丁恢复，原已交付commit dfa6723与素材未受影响；其余SAPI资产树仍在。必须保护/移出cache，先保存最小可恢复检查点，不再盲建整树副本。

人工当前0必做，51项10/19/22≈38%、首产品27%暂不变；技术债最终按实际处置更新，不假报全部问题解决。缓存事故不导致Goal全局blocked。

## 重复工作副本核算与退役

`.cache/cache-source-copy-audit.json`实测67个登记副本（除主树），66个可读副本跟踪源码逻辑体积290,308,033字节（约276.9MiB）；不能将其称为58GiB。9个近期副本逐文件git hash-object与已提交eb6addf/81af166/dfa6723对照，只有clip-speed-frontend和replacement-ui完全一致且无用户资产；无活跃测试/媒体进程、逐级绝对路径与无reparse校验后以git worktree remove退役两棵，共14,256,658逻辑字节，未制作整树备份。审计`.cache/worktree-retirement-audit.json`和result.json。剩余含未知中间版本的副本不凭名字批删，记录TD018部分，继续按来源/未提交内容核清，不让历史堆积阻断产品主线。

本次保护与止血已交付；TD018整体部分完成（遗留工作树/失踪目录未全部核清），债务由17项10/2/5变18项10/3/5，功能及人工数字不变。用户无新增操作要求。下一恢复主树本地旁白，不重建cache工作树，不重跑已完成广泛测试。

## 活动目录消失的有界独立核查

Luna/high只读定位到主会话原日志`C:/Users/Crux/.codex/sessions/2026/10/28/rollout-2026-10-28T23-29-29-01a18321-6fde-7e33-a815-a466d2e12007.jsonl`：第7447/7449行UTC07:41:45创建narration-integration，第7718行UTC08:02:28已报告缺失并由用户否认手删；两时刻间未找到指向该目录的删除调用。第8134/8136行UTC08:48:31后续worktree退役实际结果只含clip-speed-frontend和replacement-ui，时间晚且清单不含目标，故不是首次消失来源。证据不足，保持未归因；不把查不到工具记录等同没有外部进程删除。
