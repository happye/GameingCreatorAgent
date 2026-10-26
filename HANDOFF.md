# 当前交接：工作台可识别画面文字、完整verify恢复通过；仍等待用户确认分组与补素材

## 新对话接手清单（2026-10-25，Claude Code会话交接，最先读这里）

**进度看板**：用户量化监督入口为[docs/exec-plans/progress-board.md](docs/exec-plans/progress-board.md)；每次重大改动必须同提交更新（规则见AGENTS.md“Persistent progress board”）。

**第五会话（2026-10-27，最新，Claude Code；用户以/goal要求持续推进）**：
- 登记预填（98c6035）独立评审已重跑：code-quality-guard（opus）PASS，无P0／P1；4个P2全部修复（指南说明证据只跟随盘点生成页、分钟计数标“含重复／共用画面”、盘点报告同一路径两次整体拒绝、盘点报告专属错误提示）。
- 发现第四会话最终HEAD的完整verify其实会在mypy静态门禁失败（`scripts/prepare-benchmark-plan.py`冗余cast，该会话只跑了定向测试）；已修。修后完整verify（源码=e321523＋该一行修复，期间未改代码）：**3638 passed／0 failed／3 skipped（15分04秒）、`All project checks passed`、退出码0**（.cache/verify-20261027-session5b.log）。
- 新交付：工作台“画面文字（本机识别，不花钱）”卡片（`frame-text-v1`，[sprint](docs/exec-plans/sprint-frame-text-panel.md)，[指南](docs/references/ocr-frames-guide.md)“在工作台里用”）：点击后复用`ocr-frames`本机识别（快速约每2秒一帧／完整），缓存在仓库`.cache/workspace/frame-text/`，原片／取帧时刻／引擎变化即失效；列出反复出现文字、点击跳转、按词查找（30秒内合并）。真实长钟馗快速76秒、476帧中57帧有文字，“大蚌”→09:12–09:24与10:08–12:43（Boss战）。定向测试与内置浏览器走查通过。独立评估gc-reviewer（sonnet）PASS、无P0／P1，5个P2中4个已修、1个记为已知限制（补装语言包后需手动重新识别），见sprint第五节。
- 离线候选排名工作流（3视角侦察9候选＋3评委）：第一“验收第2步原片标注页省力辅助”8.05，第二“工作台时间轴标出画面文字／镜头并按键跳转”7.65，第三“防止同一视频重复付费分析（§52缓存守卫）”7.1；“剪辑篮FCPXML导出”因属后续阶段被判0分。
- 新交付：原片标注页省力辅助（[sprint](docs/exec-plans/sprint-reference-page-aids.md)，[指南](docs/references/benchmark-reference-review-guide.md)“省力的辅助”）：主查询“x/10还差y个”、已登记区间条（点击跳转）、不同事件重叠先提醒再确认、键盘I／O标记起止（复用时钟保护）、逗号／句号约一帧、[ ]调速；记录格式与核对规则不变。三视角评审工作流PASS无P0／P1，P2已修；真实长钟馗页面实测通过。
- 看板：OCR仍🟡，整体仍27%（10✅／8🟡／33⬜），技术债与人工待办数不变。下一步：完整verify，然后做排名第二项。

**第四会话（2026-10-26，Claude Code；用户以/goal要求持续推进，已于额度不足9%时收尾）**：
- 完整verify（会话开始时启动，期间写入TD017与镜头切分代码，新测试文件未被收集）：3600 passed／0 failed／3 skipped、`All project checks passed`、退出码0（.cache/verify-20261026-session4.log）。提交51ef13a后另跑一次完整verify：3621 passed／0 failed／3 skipped（15分01秒）、`All project checks passed`、退出码0（.cache/verify-20261026-session4b.log）。
- ~~TD017~~已解决：验收就绪摘要默认读全部任务页（命令行／工作台不再只读最新100个）；显式分页且未见可检索运行时报`unknown_partial_task_snapshot`而非“没有可检索运行”；A/B/D待决定只在确有覆盖缺口任务时出现。
- 新交付`detect-shots`（shot-boundaries-v1，[sprint](docs/exec-plans/sprint-shot-boundaries.md)，[指南](docs/references/shot-boundaries-guide.md)）：本地只读、不花钱，检测原片镜头切换与黑屏，并标出已保存事件／多帧分析窗口是否跨镜头。长钟馗：41切换、10黑屏段；272窗中41窗（约15%）跨镜头；被拒第21窗跨2个切换，第248／253窗不跨。抽查2处为真实切换，准确率未人评。看板：场景切分⬜→🟡，整体25%→26%；技术债已解决8→9。
- 工作台：左侧“镜头切分”卡片一键检测（缓存于仓库.cache/workspace/shots，分析变化即失效），时间轴切换刻度与“跨N个镜头切换”标签；内置浏览器实测通过。重建窗口经阶段输入哈希比对：长钟馗272窗0不一致。
- 独立评估：code-quality-guard（opus）两轮——首轮FAIL（审查中途代码写坏的P0＋工作台缓存P1，均已修），复审PASS；剩余P2已修或记为已知限制（sprint第四、五节）。
- 新交付`ocr-frames`（ocr-frames-v1，[sprint](docs/exec-plans/sprint-ocr-frames.md)，[指南](docs/references/ocr-frames-guide.md)）：用Windows自带中英文识别读取任务取帧时刻的**原分辨率**原片画面文字（重取帧须与保存时刻整列相等）；不下载、不花钱、只读、不进检索。长钟馗1903帧／263秒，读出Boss血条名“大蚌真君”约550–763秒、片头“游戏科学”、片尾开发版声明；数据库不变。选题来自三视角侦察＋评审工作流（8.1/10），评估为三视角评审＋反驳核实工作流：均PASS、7个P2全部已修。看板：OCR⬜→🟡，整体26%→27%。
- 素材盘点黑屏比例：已核实原盘点把Atom录音（552帧有效画面0）列为“无法比较”，无需改动；不再列为候选。
- TD007离线归因（只读汇总）：41个跨镜头窗中39个在过场，玩法段仅2个；过场内跨／单镜头拒绝率与标签数几乎相同。结论：本素材跨镜头不是玩法理解差的主因，暂不提按镜头切窗口的付费提案（记入TD007与sprint-shot-boundaries第七节）。
- 验收第1步可从素材盘点报告开始：工作台“验收流程”第1步或`prepare-benchmark-plan.ps1 -InputPath <盘点报告>`，自动列出编号与路径，录制组／用途／声明／查询全部留空，每段旁显示盘点证据（不写入草稿或计划），上方实时计数组数与开发／测试分钟。真实17素材报告实测页面正确；71项定向测试通过。**独立评审未完成**：两视角评审工作流因用户额度不足收尾而中止、无结果——下一会话第一步重跑它（脚本：本机会话目录workflows/scripts/review-registration-prefill-*.js，或按同一提示派code-quality-guard审`application/benchmark_plan_draft.py`的`inventory_to_draft`、`scripts/prepare-benchmark-plan.py`、`ui/benchmark_plan_editor.py`、`ui/static/benchmark-plan.js`）。
- OCR提交e5c54e8的完整verify：3626 passed／8 failed／7 errors／3 skipped（.cache/verify-20261026-session4c.log）。失败全部在`test_benchmark_workflow*.py`，原因是运行中途改了登记预填代码（`ImportError: inventory_to_draft`，进程先载入旧模块、子脚本读到新代码），不是产品缺陷；对最终HEAD 98c6035单独重跑这两个文件48项全部通过。**最终HEAD尚未跑过一次不受干扰的完整verify**。
- 下一会话顺序：①重跑登记预填评审并处理问题；②对最终HEAD跑一次完整verify（期间不要改代码）；④再做一轮离线候选排名（工作流）。主线仍等用户分组决定（不催）。本会话于用户提示额度不足9%时收尾。

**第三会话收尾（用户额度不足主动收尾）**：
- 已push到origin/main（c5a3c83及其后收尾提交，见`git log origin/main -1`）。本会话交付：跨改动审查及两P2修复、TD008预览缓存ChangeTime、TD012批次路径、TD005检索期间文件变化重哈希、TD003来源核对、TD005第B步测量；F006验收流程两轮对抗审查——第一轮1个P0（计分去重）＋4个P2＋1降级项全部修复（见[sprint](docs/exec-plans/sprint-f006-pipeline-review.md)），第二轮无P0／P1、3个P2。
- 第二轮P2处理：①失败查询的计数改为null而非0、部分判定时`usefulIndependentEvents`为null——代码与2个新测试已写（`application/benchmark.py`、`tests/test_benchmark.py`），提交状态见下一条；②③验收就绪摘要两处显示问题记为TD017，未修。
- 第二轮P2①已提交并push（`fix(F006): report unknown counts for a failed query`），基准测试文件全部通过、Ruff／mypy通过；未另跑完整verify。**下一会话第一步**：可先跑一次完整`verify.ps1`确认，再做TD017（小）或等待用户分组决定。本轮最后一次完整verify为3598 passed／0 failed（源码5879f98）；该P2修复只跑定向测试。
- 不变：Phase 0；F006／F009／F010仍false；无付费调用、无待批费用提案；用户尚未决定素材分组（不催）；TD005第B步是否并行哈希待业主决定（热缓存4线程1.14→0.67秒）。`.codex/agents/gc-*.toml`九个未跟踪文件非本会话所建，未动。

**第三会话（最新）**：上一会话遗留的三件事已处理——①session2c的verify为3588 passed／2 failed，2项`test_writer_lock`子进程无输出发生在会话退出、控制台被关闭期间，单独重跑通过；本会话重跑完整verify结果见下一行；②跨改动审查（`ad6be26..HEAD`，code-quality-guard opus）PASS，无P0／P1，两P2已修（TD012批次路径`resolve_existing`；TD005检索期间文件变化则保存前完整重哈希）；③已普通push：origin/main由ad6be26更新到6286d80（含上一会话与本会话全部提交）。另交付：TD008视频预览缓存签名加NTFS ChangeTime（同大小改写＋恢复修改时间现可识别）；TD012`MediaBatchFiles`同类路径竞态；TD003核对到原FFmpeg日构建已无法从BtbN重新取得（只留月末构建），发布前须换固定一个可取得构建并经用户许可下载。`.codex/agents/gc-*.toml`九个未跟踪文件是其他工具／用户于2026-10-25 19:33创建，本会话未改、未提交。Phase 0不变，F006／F009／F010仍false，无付费调用。
**F006验收流程审查（第三会话后段）**：4维度审查＋每个P0／P1三票反驳的工作流找到1个P0：前十名里某事件先出现0/1分片段，会让后面同事件的2/3分片段算重复记零，能过关的主查询可被判6/10不过关；已修（Python计分与`score-retrieval.ps1`），code-quality-guard PASS。另修4个P2与1个降级项：同文件登记两次冻结即提示、标注页禁止两名称共用一个动作归组、登记表单改编号不再搬走别的录像的查询、重跑已完成第2步先确认、指南冻结命令补`-AutoInventory`。正式人工评分尚未开始，无真实结论改变。见[sprint](docs/exec-plans/sprint-f006-pipeline-review.md)。完整verify（源码HEAD 5879f98）：3598 passed／0 failed／3 skipped（14分11秒）、`All project checks passed`、退出码0（.cache/verify-20261025-session3c.log）；已push。
**TD005第B步测量**：真实15分钟任务热缓存下4线程完整核对1.14→0.67秒（约41%，过30%门槛），收益来自原片与证据帧同时计算，冷缓存未测；仍待业主决定，见sprint-inspect-integrity-single-pass.md末节。
**第三会话verify**：对8daef7c（运行期间陆续加入TD008／TD012修复）完整`./scripts/verify.ps1`为3590 passed／0 failed／3 skipped（14分29秒）、`All project checks passed`、退出码0（.cache/verify-20261025-session3.log），`test_writer_lock`本次通过。对最终HEAD（含TD005与MediaBatchFiles修复）另跑一次，日志.cache/verify-20261025-session3b.log；结果：3592 passed／0 failed／3 skipped（14分58秒）、`All project checks passed`、退出码0（源码HEAD 275acba，其后仅文档提交）。

**当前状态**：本会话（2026-10-25第二会话）在main本地新增提交22d886a／389155e／e58fc1a等，尚未push；对e58fc1a跑完整`./scripts/verify.ps1`为3566 passed／0 failed／3 skipped（14分30秒）、静态门禁与离线包通过、退出码0（日志.cache/verify-20261025-session2.log）。注意：在PowerShell 5.1里用`*>`重定向verify会把uv的正常stderr当成终止错误，应从bash调用`powershell -File scripts/verify.ps1 > log 2>&1`。Phase 0；F006／F009／F010仍false；无新付费调用、无待批费用提案。

**上一会话交付（详见下方各节与sprint）**：TD012工作台状态文件竞态修复；只读素材盘点`inventory-sources`（source-inventory-v2，识别黑边／镜像）；`benchmark-freeze-v2`冻结强制核对盘点并默认自动盘点；TD015检查门禁恢复与TD016联合检索回归修复；三个中文ps1加BOM适配PowerShell 5.1；验收流程浏览器八步走查与阻断／就绪提示中文化；`.claude/agents/`九个Claude角色合入。

**用户决定**：2026-10-25答复分组尚未决定，先做离线工作；在用户主动提出前不再催分组或补片（见human-inputs）。

**下一步按顺序（均离线、不花钱）**：
1. ~~TD012媒体准备偶发“准备项目须位于当前仓库的artifacts目录内”~~：2026-10-25已复现并修复（并发删除数据库时`resolve()`约9%返回`\\?\`／`$Deleted`路径；改为`lstat`链接检查，新增并发与链接两测试，22项通过）。见tech-debt TD012 2026-10-25段。
2. ~~TD005真实长素材资源~~：2026-10-25实测钟馗15分52秒准备25.1秒／进程树峰值227MiB，两段盘点35.8秒／226MiB，工作台详情1.7–2.3秒（一小时估7–9秒，候选优化触及存储边界，已记TD005待评估）。~~TD002~~：OBS式MKV／WebM缺`duration_ts`现逐包补探测（仅matroska／webm，MP4不变），code-quality-guard PASS；真实6分钟钟馗转MKV经CLI准备成功，内置Chromium可预览播放。
2b. ~~TD012 WinError10053~~：`ui/server.py:do_POST`改为先读完有界请求体再拒绝错误Content-Type／超限请求（超限最多丢弃读取1MiB）；压测旧代码400次中2次10053，修复后1600次全收到400，新增并发回归测试。~~TD012“取消范围400而非404”~~：根因是Windows非严格`resolve()`遇父目录被并发创建时保留`\\?\`前缀；新增`infrastructure/local_paths.py`（`resolve_existing`／`is_link`），并经工作流扫查全仓约180处`resolve()`后修复另4处同类问题（精分析sidecar、嵌入缓存、静态观察账本路径、联合检索目录）。TD012仅剩跨进程状态文件占用。
2c. ~~TD005详情加载优化~~：实测拆分后决定暂不改（主要耗时是每次打开的完整性哈希这一保护，要改需“按文件身份缓存哈希”的设计决定，关联TD008），已记TD005。
2d. 本会话后段（均已提交）：目录扫描纳入MKV／WebM（`domain.media.LOCAL_VIDEO_SUFFIXES`）；验收页时钟映射按容器固定测试（零起点MKV／WebM与音频晚起WebM精确，非零起点MKV／WebM与音频晚起MKV退回手动）；TD011在独立Windows PowerShell 5.1验证通过后关闭；验证脚本report.json遇外部句柄的WinError5改为有界等待；TD013冻结后未建库的批次可续跑（命令行与工作台同一规则，其他任何痕迹仍拒绝，code-quality-guard PASS）。
2d+. TD005第A步已交付（见sprint-inspect-integrity-single-pass.md）：工作台带查询打开每文件哈希3→1次，真实15分钟打开约1.7→1.0秒，保证不变，code-quality-guard PASS。第B步并行哈希、界面“已核对”小字、一小时冷缓存首次等待是否调大，列为业主决定事项（见该sprint第七节）。本批前一轮完整verify：3584 passed／0 failed／3 skipped。
2f. ~~上一会话未完成三项~~：第三会话已处理（verify结果、跨改动审查PASS及两P2修复、push，见本清单顶部“第三会话”）。原记录：①对e58fc1a之后全部提交的整仓verify正在跑（日志.cache/verify-20261025-session2c.log），结果若未补记在此，下一会话先读该日志末尾；②全会话跨改动审查工作流（4视角＋每发现2票核实）因额度停止、无结果，脚本在本机会话目录`workflows/scripts/session-cross-change-review-*.js`，下一会话可用同样提示重跑（范围`git diff ad6be26..HEAD`）；③本会话所有提交仅在本地main，尚未push。
2e. 剩余离线候选：TD012跨进程状态文件占用（仅再现时评估有界重试）；检查与使用之间的junction换入（需句柄式打开，L）；TD008哈希缓存身份；TD003发布前固定FFmpeg来源。下一会话可从这里或总方案下一阶段规划继续，仍不催分组。
3. 若用户确认分组或补了原始游玩录像：工作台“验收流程”冻结步骤默认自动盘点即可核对；新付费分析必须先给具体提案并获明确批准。

**环境规则（违反会造成假失败或破坏工具链）**：Python一律`-B`并设`PYTHONDONTWRITEBYTECODE=1`；测试在仓库根、先`. ./scripts/env.ps1`；pytest用`-W error -o cache_dir=.cache/...`，不要与`-p no:cacheprovider`同用；推送用`git -c http.proxy=http://127.0.0.1:7890 -c https.proxy=http://127.0.0.1:7890 push origin main`；子Agent隔离worktree需`.tools`目录链接，清理前先单独删链接（见Claude分工指南）。用户本机只有Windows PowerShell 5.1。

**Claude角色**：新会话从仓库根启动后先用`/agents`确认9个gc-*角色出现，并补记到[Claude分工指南](docs/references/claude-agent-routing-guide.md)；未出现时按指南回退方式派发。

**浏览器说明**：上一会话的浏览器标签是Claude自己的内置浏览器，用于本机8791端口测试工作台，不需要用户操作；会话结束时已关闭预览服务器，所以标签打不开属正常。走查留下的“Claude 冒烟测试 2026-10-24（可删除）”流程可由用户在工作台删除，不影响正式数据。


更新：2026-10-24，Phase 0，main。新准备的两种验收页面，对已验证Chromium／MP4非零PTS及异步音视频可自动换算、取时、定位同规范区间并末停；未知／不支持仍手填。旧页面包、原12标注及纠正保持，不要求重标。见[报告](docs/exec-plans/report-2026-10-24-source-clock-mapping.md)、[sprint](docs/exec-plans/sprint-source-clock-mapping.md)及[当前里程碑](docs/exec-plans/current-status.md)。

## 已交付与验收

- TD006：正式256passed／0skip、九文件Ruff／格式／五源码mypy／三JS语法通过，原Sol/high R1–R8 PASS。实际旧编辑包＋10有效参考经生产CLI复用成功，37保护／922原项目SHA不变。12源码／测试SHA与Git blob前后相同。仅实证范围通过，不是逐帧裁切或通用编码兼容。
- 单注册帧真实试验已结束：原28.5秒图＋parts-v2唯一一次HTTP200，1主体／7typed属性，另进程正例1／跨衣物负例0，本地resume零发送。估算¥0.001492（1016输入／119输出tokens，未核账单）；¥0.50许可的一次额度已用尽，剩余钱不允许追加。run f601fb9b3e734d5ea188fc15c790acbb，attempt205f8efdee85311c7190dfc57bfb4a13。见[试验报告](docs/exec-plans/report-2026-10-24-static-observation-pilot.md)。
- 静态声明导入／parts查询、单帧prepare／具体授权／一次发送／本地resume，以及TD014状态可靠性均已交付；历史证据沿原报告保留。F006／F009／F010仍false，真人准确性未通过。

工作台扩展组原2项失败已修复（2026-10-24 Claude Code）：根因是Windows替换正被读取的状态文件会被拒绝（WinError5），验收流程status.json与素材批量state.json现由进程内锁串行；同组还更新了一条与ce934e0免责文字不符的过时断言。扩展10文件129项全部通过，独立code-quality-guard PASS；整仓verify未重跑，跨进程占用仍归TD012。见[sprint](docs/exec-plans/sprint-workbench-status-replace-race.md)。Claude原生九角色已合入（`.claude/agents/`，见[Claude分工指南](docs/references/claude-agent-routing-guide.md)），新会话需用`/agents`确认发现。

## 2026-10-25验收流程浏览器走查与提示改进（最新，本会话收尾）

内置浏览器用真实素材完整走通`/acceptance`八步（流程“Claude 冒烟测试 2026-10-24（可删除）”）。修复：关联步骤选错用途时原因被吞成“读取失败”（现显示具体原因）；冻结阻断、就绪阻断和“仍待你决定”代码改为通俗中文说明（代码保留括号内）。相关测试通过；就绪中文说明已在主工作台“验收就绪”对话框实际复核显示正确。

**最终状态**：2026-10-25对HEAD（9415062起，含全部本会话改动）跑完整`./scripts/verify.ps1`：静态门禁通过，3538 passed／0 failed／3 skipped（12分57秒），`All project checks passed`、退出码0。

**下一会话恢复顺序**：用户2026-10-25答复“分组还没决定，下一会话先继续离线工作”。因此①直接按technical debt推进离线项（TD012高负载偶发、TD005真实长素材资源、TD002时钟补探测等），不重复催分组或补片；②用户之后若确认分组或补了原始游玩录像，再用工作台冻结（默认自动盘点）核对；③新付费分析须先给具体提案。新会话从仓库根启动后用`/agents`确认9个gc-*角色并补记[Claude分工指南](docs/references/claude-agent-routing-guide.md)。

## 2026-10-24冻结时自动盘点

工作台冻结步骤默认勾选“冻结时自动盘点登记的录像”，CLI为`freeze-benchmark --auto-inventory`／`prepare-benchmark.ps1 -AutoInventory`：不必先单独运行盘点命令，冻结时本机自动比对计划内来源并打包报告，异组共用画面直接给出阻断。真实Atom异组计划12秒被拦；浏览器端到端走查通过，阻断改为通俗中文说明。完整verify 3517 passed（1项TD012偶发）。见[sprint](docs/exec-plans/sprint-freeze-auto-inventory.md)。

## 2026-10-24盘点识别黑边与镜像

`inventory-sources`报告升级为`source-inventory-v2`：自动裁掉均匀黑边再比对，并额外比较左右镜像；冻结同时接受v1与v2报告。真实验证中加黑边与镜像的同源片段由“认不出”变为在正确偏移报告；17素材重跑无新增误报（仍仅Atom PV／实机）。见[sprint](docs/exec-plans/sprint-inventory-crop-mirror.md)。新报告`artifacts/source-inventory-20261024/report-v2.json`。

## 2026-10-24冻结计划绑定素材盘点

新冻结一律为`benchmark-freeze-v2`：`freeze-benchmark --inventory <盘点报告>`（工作台冻结步骤可上传）把报告原样打包并核对每个来源；缺盘点、来源缺失／失败／无法比较、共用画面分到不同组或跨开发／测试都会阻断就绪。v1保持字节不变但不再能给出独立测试集。真实反例（Atom PV／实机异组）被拦下。326定向测试通过、code-quality-guard PASS。见[sprint](docs/exec-plans/sprint-freeze-source-inventory.md)。下一步仍待用户确认分组与是否补原始录像；离线可继续的是F009／F010等不依赖人工的改进。

## 2026-10-24正式检查门禁恢复

`verify.ps1`静态门禁恢复通过；全量不再在20%处挂起（3440 passed，余3项为TD012高负载偶发、单独通过）。修复了已交付功能回归TD016：多录像联合检索hybrid／semantic（含“已有细节”）保存失败，真实数据实跑恢复；三个中文PowerShell脚本加BOM后可在用户本机PowerShell 5.1运行。见[sprint](docs/exec-plans/sprint-verify-gate-restore.md)。下一主线：按[freeze-v2合同](docs/exec-plans/sprint-freeze-source-inventory.md)让冻结计划绑定素材盘点。

## 2026-10-24素材来源盘点

新增只读命令`./scripts/inventory-sources.ps1`：本地探测时长／编码／SHA并检测不同文件间共用画面，不分组、不调用模型。实跑17素材：代号：Atom的PV与实机共用画面（PV晚10秒），Atom录音275秒画面全黑只有声音，新增6个TapTap文件均30–128秒短展示片；可用长录像仅钟馗两段。见[盘点结果](docs/exec-plans/source-inventory-2026-10-24.md)与[sprint](docs/exec-plans/sprint-source-footage-overlap.md)；52项定向测试通过、gc-reviewer PASS。已在[人工清单](docs/exec-plans/human-inputs.md)请用户确认分组、是否补原始游玩录像。另发现main静态门禁失败（TD015），下一步先机械修复并跑一次完整verify。

## DSH恢复入口与加载

- 配置：个人Skill codex-dsh-collab（本轮核最新版SHA c36cc6c2…854a），toolRoot G:/Tools/ChatGPTRepo/codex-dsh-双端联通，stateDir C:/Users/Crux/.codex/codex-dsh-state，native http://127.0.0.1:3080，workspace f4395711-a8fb-49a3-ad95-7305ce9ea1e8。
- TD006 task gamingcreator-source-clock-mapping-20261024／session codex-94269cc4-7c00-4bbe-917e-bdd6205a1a9f。四请求29a141ad／87da2a18／b90f9594／93834a15全部COMPLETED，完整终态报告各按hash读一次；当前无watcher、无源码写者，**不重投**。最终合同v6 `1155ea481af6e9e3507250ddb5b56c8a6b660d87b7ef485dadd4fd512b3c7311`。结果、回执与源码证据在ignored artifacts/dsh-source-clock-mapping-20261024/。
- v2漏登记27个ignored只读条目形成的scope阻断已恢复。隔离工具分支codex/contract-enrollment-20261024提交51f42dd；一次显式baseline-supplement只追加27项，原654条目和Git身份不变，旧资产保留，configured原CLI已正常bind/run。主工具安装仍fc47d97；不手改旧ledger、不移动材料、不另建任务绕门。
- 旧静态task gamingcreator-static-observations-20261023／session codex-35d31548-8d46-4f1b-b8dc-1886e7f8f355：本轮已核running=false、queue0、三请求COMPLETED；STOP_PENDING／STOP_ACTIVITY_UNRESOLVED继续保留。不再cancel、杀共享Host、归档或重发。Skill／手册更新已由CLI当前磁盘导入，不需要重启现有Host。
- 主控额度中断后可从原会话恢复报告；不能承诺停顿期间自动验收／派下一轮。本轮已纠正用旧RUNNING结束监督的问题，单watcher60秒cursor／generation增量，终态及时读一次结果。工程模型用量另存且关联有限，未知费用不补零。

## 保留进度、人工依赖与下一步

长钟馗269成功／3拒绝／469观察保持，原片约15分52秒，842.598秒是续跑墙钟；累计API估算¥1.49022124，本rununknown／预留0，其他未知账独立保留。3缺口仍非Completed；用户选C离线改进，未代选A/B/D，不补窗或重跑成功窗。

已有12标注与用户纠正（10有效：Boss1／连招5／剧情4）、六新增素材全部保留，当前不要求重做或再补文件。只读来源对齐证明10正例对应钟馗failed／coverage_gap，32旧排名均异源，无同源Completed可作有效覆盖投影。F006须原来源独立性／事前参考／明确Completed绑定／固定Top10人评；原v5画面对错按“稍后核对”留空。

工作台可靠性已处理；下一回原真实质量计划，复用已有资料；仅在实际触发来源确认、新参考或具体新费用提案时按[人工清单](docs/exec-plans/human-inputs.md)提醒，不重复催同待办。不转入后续成片／正式桌面／商业阶段。发布状态另见本文件末尾及本机publication.json，不能从旧网络失败推定当前远端。

发布：功能／报告提交`c8b9667`已普通push成功（origin/main从e9361e2更新到c8b9667），此前单帧试验文档9e8e525和0790976亦已同步。25文件保存，12个已验源码／测试Git blob与最终提交一致，工作树干净。此前GitHub连接失败为历史，不是当前阻塞；隔离工具修复51f42dd仍仅本地工具分支，未合入主工具安装。

后续发布状态：补记上述成功事实的文档提交`23a812e`第二次普通push遇GitHub:443连接失败；该文档及本条记录本地保存，未称远端已同步。远端已确认源码仍c8b9667，功能和验收不受影响。本节点不再push；后续有实质交付时一起普通补推，不能据网络失败重跑DSH／旧录像任务。
