# Errors

## 2026-10-08 分组排名检查准备

首助手误写local_embeddings模块名（0查询）、首patch上下文不匹配（未写入）、类型循环变量复用、检查夹具candidate_sources单源API及旧合并文本断言，均按实际代码直接纠正并保留首日志。全套一次2402passed／3旧failed／3error／1skip，TD012／TD014根因未解，不重跑；没有修改旧工作流或冻结模型结果。

## 2026-10-08 人物语义检查准备

完整入口第一次在pytest前被health测试新增能力行的缩进挡住，按formatter一次修正；首日志detail-actor-full-verify.log保留。实际套件只跑一次，2389passed／1旧TD014失败／1权限skip，不循环。代码未改旧工作流；源码冻结后包检查与现用继续。恢复时区分准备检查失败与已执行完整套件，不覆盖原回执。

## 2026-10-07 统一验收验证假设错误（已直接纠正）

首次新后台检查因补丁缩进错误未收集；修正后15passed。浏览器首两项使用CSP禁止的字符串求值，改函数后2passed，不改安全策略。新增候选播放夹具先撞旧目录、再漏子目录创建及继承特殊时钟，全部保留原回执；按实际asset修正后1passed。真实助手初次旧漫画manifest路径少media层、随后链接名称错，保留已保存七步并从原流程完成评分，未重搜；尾部误假设DB字节必变和benchmark额外写检索JSON，只读实际SQL／原表与文件后改核验。见.cache/benchmark-workflow-*及artifacts/benchmark-workflow-validation，避免重复搭建或把验证假设称产品缺陷。

## [ERR-20261007-023] benchmark_fixed_scoring_fixture_and_types

**Logged**: 2026-10-07
**Area**: tests / application

首轮类型检查4项：object数值先明确cast、Protocol callback参数名须匹配media、JSON字典赋值需类型明确、已收窄SHA重复cast移除，直接修正后81范围通过。新测试猜错snapshot模块导致收集失败，按现有review测试引用test_detail_query修正；篡改用例把context.template共享对象当下载记录，补deepcopy后正确拒绝。最终116定向通过3.53s，原评分／费用合同未放松。恢复须复用已知fixture入口，不猜路径；完整及实际验收以sprint／回执为准。

固定计分完整2095passed／1权限skip及实际三开发片零新增检索／832项目文件保持通过，旧TD012未重现但不判原因解决。验证后仅文档／ignored证据更新，不再重复源码全套。

## [ERR-20261007-022] benchmark_review_check_scope

**Logged**: 2026-10-07
**Area**: tests / scripts / documentation

首轮mypy使用Mapping解决容器方差，37定向行为含音频fallback和浏览器迟到载入保护通过；Ruff未使用context直接补质量null断言，未循环调试。PowerShell检索模式中的双引号引发解析失败，改单引号一次；不存在路径／glob换成实际文件。一次文档批次最后hunk猜错标题，整批未落盘；读取精确标题后重做。不得用最后一个检查的exit0掩盖之前错误，不猜路径／标题。完整检查和实际三源回看结果以sprint及回执为准。

完整2069passed／2旧测试Windows环境失败／1权限skip：HTTP错误类型测试WinError10053、pilot JSON替换WinError5。源码未改，窄复查一次2passed1.11s，保留初次失败／TD012，后续补CLI和双离线包检查；不反复诊断或重跑全套。查.cache文件应限顶层，禁止递归扫描旧锁目录；读取模块先用rg --files限定src确认文件名，不猜material_tasks路径。

## [ERR-20261007-021] benchmark_preparation_fixture_and_wrapper

**Logged**: 2026-10-07
**Status**: resolved; focused133 / full2034 and actual PowerShell Freeze/Bind passed
**Area**: tests / scripts

新测试重复猜测不存在的helper导入两次，最终按现有定义使用test_detail_query.snapshot；沿已有规则先rg定义再import，不猜模块／符号。两断言直接修正：确认参考后的空返回应失败，验证未判分应返回一个未判分候选；storage fixture不能同目录重复建media，复用一次bundle。CancellationContext须run_id、mypy冗余cast与--binding参数误接search均由类型检查直接纠正。测试新代码先format再lint，避免紧凑一行语句造成噪声。公开PowerShell wrapper最初错误从根目录找env.ps1，直接改scripts/env.ps1，真实中文Freeze／Bind通过；首失败回执保留，不调查全局环境。一次文档补丁引用了不完整行而未应用，按完整现有行重做，未改生产源码／重复完整测试。

## [ERR-20261007-020] material_tasks_audit_assumptions

**Logged**: 2026-10-07
**Status**: direct test/script fixes resolved; actual hour inspection latency deferred TD005
**Area**: tests

两条迟到响应测试用了wait_for_function字符串布尔式，被既有CSP拒绝；直接改已有函数形式，不放宽CSP，完整1987／1权限skip通过。实际脚本最初猜测URL project参数能切项目，按原手动表单纠正；5秒小时完整详情等待不足，退出时handler尚未结束引起清理错误。未认定新生产bug，停止该耗时探查，最终6真实清单页面字节保持，明确小时完整详情未验证，小型任务打开／禁搜由行为测试覆盖。Shell读文件使用了Bash brace路径导致PowerShell解析失败，直接显式列路径；health拒连后应先止错判断服务终止，不继续使用null响应。旧health拒连／父子CIM不存在后正常隐藏启动新服务，完整身份再核对通过，不盲停历史PID。

## [ERR-20261007-019] media_preparation_test_contracts

**Logged**: 2026-10-07
**Status**: resolved; focused65 and full1942/one permission skip passed
**Area**: tests

新离线准备测试最初遗漏非v1 prompt hash、把SamplingParameters.interval_seconds写成interval、把已结束metadata用于begin_invocation，并错误预期configuration.invalid为输入退出2（原合同为环境退出3）。按已存在类型／保存／调用合同直接修正测试，不放宽生产校验。CLI首次read_only参数拼写由mypy直接纠正。一次定向运行全部用例结束后因未预建新cache目录触发已知Windows pytest目录rename权限错误；直接按verify已有做法创建当前新目录，未调查权限或删除旧目录。后续定向65passed（20.53s），更早95passed／5错误断言及cache失败回执保留。所有后续独立测试先建cache目录；不在旧问题上反复排查。

## [ERR-20261007-018] media_wrapper_types_and_shell_host

**Logged**: 2026-10-07
**Status**: resolved; Windows PowerShell 5 compatibility deferred as TD011
**Area**: tests

流式接口初次适配的测试wrapper漏标注kwargs，strict mypy直接报错；改为明确Callable参数转发。真实离线入口测试在Windows PowerShell 5子环境因Get-FileHash不可用失败，UTF-8读取旧shell错误还产生线程解码警告；移除继承模块路径后仍失败。按用户优先级停止该局部兼容调查，记录TD011，使用工作站已有且完整环境检查通过的PowerShell 7验证入口，不改全局配置或安装组件；脚本输出UTF-8仅当前进程，测试失败直接显示stderr。Core7入口本身首次已成功，但新断言误把仓库内临时源的相对路径当仅文件名；按实际支持两种来源的输出合同检查末级中文文件名后通过，未改报告来源身份。

## [ERR-20261006-017] long_retrieval_fixture_boundaries

**Logged**: 2026-10-06
**Status**: resolved
**Area**: tests

长事件首轮定向检查四失败：2051向量写入Windows真实缓存超过测试helper的10秒默认期限；65ms跨批超时测试被文件I/O提前消耗；1280短区间却复用100ms图片，违反原证据重叠合同。测试使用120秒容量期限／留充分余量的总超时对照，并为每个合成事件注册对应时间证据，不放宽生产取消或证据规则。二轮定向全部通过。源路径检索再次猜测不存在的文件，已有ERR-015规则仍适用：先rg --files后读取。

## [ERR-20261006-016] browser_wait_keyword_argument

第二次核验又因非函数形式wait_for_function被页面CSP禁止动态eval中断，追加1普通搜索，0Provider；改为函数表达式，不放宽生产CSP／bypassCSP。两次失败分别保留回执，正式四搜索另计。真实浏览器核验脚本先用明确函数及arg=，复用实际已通过的调用形式。

**Logged**: 2026-10-06
**Status**: resolved
**Area**: tests

动作前后文真实播放脚本首次把wait_for_function的arg当位置参数传入，TypeError发生于首个Atom查询后；evaluate允许位置参数，wait_for_function使用arg=关键字。修正实际调用，首次新增1条普通本地搜索，无Provider／费用。保留失败记录；最终实测的4条搜索与首轮1条分开计数，不声称所有检查首次通过。

## [ERR-20261006-015] guessed_source_filename

**Logged**: 2026-10-06
**Status**: resolved
**Area**: workflow

动作边界恢复时直接搜索猜测的deepseek.py／app.css／browser测试和guide文件名，实际名称为deepseek_vision.py／style.css，导致只读搜索失败。先rg --files对应目录确认真实文件，再按返回路径读／搜；不要仅凭上一轮概念名称猜路径。无源码或源数据改动。

## [ERR-20261006-014] retrieval_alias_boundary_consistency

最终104定向及1823完整／1权限skip通过，JUnit0 failures／0 errors。首次完整另有presentation旧v5断言遗漏，需全repo rg版本引用；content_type用例首次失败但单独／104定向／完整复跑通过，初次native细节未完整保留，原因不明。不把复测通过写成已证明的socket原因；长验证保留JUnit。A/B别名比较事件ID和源时钟，原英文tag可能额外计BM25分，不要求不同查询的why字串完全相同。

**Logged**: 2026-10-06
**Priority**: medium
**Status**: resolved
**Area**: retrieval

首轮英文动作扩展使用ASCII边界，而既有否认过滤使用Unicode词边界，中英文混写“寻找jumping片段”会补跳跃但不认出查询动作，让“未观察到跳跃”漏过滤（2 failures）。统一复用_ACTION_MENTION的ASCII字母／数字／下划线边界，同时识别“未见jumping”，不要另建一套查询识别逻辑。另一failure为误期待“没有shooting”零候选，实际原BM25会匹配“没有”；负意图保持既有行为，不能在有限修复中虚构缺席语义。修正后243相关回归通过，弯／直引号反例另加，最终完整证据见本轮sprint。Ruff格式后的源码锚点需重新读取，避免陈旧补丁失败。

## [ERR-20261006-013] diagnostics_remote_connection

**Logged**: 2026-10-06
**Priority**: low
**Status**: pending
**Area**: integration

独立ls-remote曾成功读到0ae1a68，但随后两次普通分支push均在约21秒后因github.com:443连接失败。只读成功不代表写入可达，不报告远端已同步；保留本地b2c2a13实现和42afbb0完整验证报告，并写待发布receipt与HANDOFF。停止循环重试，网络稳定后补推当前已授权分支，独立读远端再比对，不变更代理或全局Git配置，不强推／更新main。

## [ERR-20261006-012] diagnostics_validation_setup

**Logged**: 2026-10-06
**Priority**: low
**Status**: resolved
**Area**: tests

生产读验初稿还误用v1读取实际v2已保存精分析，返回missing并非反馈丢失；按冻结候选原请求profile v2重验，3 accepted／1 rejected保留，v4不继承。不要依据示例默认profile猜真实结果身份。文档批次失败应先读取全部锚点或从刚读的全文构造补丁，不继续添加推测hunk。

新浏览器测试误猜已有预览标题，实际为“候选 #1”；切项目脚本试图填写尚未展开的details输入，须先展开“打开其他项目目录”，真实页面可直接选择已有项目。只读证据路径从DB取得时可能相对project，必须按持久化合同解析，不能按进程cwd读取。嵌套PowerShell／python -c引号曾导致SyntaxError，改用落盘脚本；不以最后一个命令exit0覆盖先前错误。修正后新30行为回归及真实1366/390十位／下载／源回看通过，原失败无新Provider或预算变化。另一次文档批次因猜架构标题未写入；已读取精确标题重做，见ERR-20261006-008，禁止未核对末尾hunk。

## [ERR-20261006-011] pilot_review_initial_check_contracts

**Logged**: 2026-10-06
**Priority**: low
**Status**: resolved
**Area**: tests

新记录合同初次strict mypy需要显式dict[str, tuple[str, ...]]，新pytest复用fixture须先赋值而非直接未用导入，并显式绑定循环回调收集容器。浏览器首次1 failed/84 passed：fieldset已有disabled但Playwright容器to_be_disabled不按交互控件判断；改为实际select/textarea禁用核验。最终87定向和1745完整通过，真实双尺寸控件禁用/空记录往返亦通过；不把测试适配问题误报为真实模型结果变化。

## [ERR-20261006-009] comparison_render_label_map_reuse

**Logged**: 2026-10-06
**Priority**: medium
**Status**: resolved
**Area**: ui

查询条件标签与实体分类标签复用同一局部映射，第二个候选渲染触发hair_color KeyError。分离query_kind_labels后由带scene的fixture及定向116/完整1683回归验证；多候选不同状态渲染须保留此覆盖，不能只检查首个缺结果候选。

## [ERR-20261006-010] comparison_file_uri_download

**Logged**: 2026-10-06
**Priority**: medium
**Status**: resolved
**Area**: ui

HTML直接file://打开时，相邻JSON相对链接未产生下载，实际点击超时。改用静态内嵌UTF8 JSON data URL与明确download文件名，无脚本或外部请求；浏览器回归验证两份下载逐字节等于落盘文件，真实1366/390模板下载亦通过。查看链接不能代替实际下载验收；原失败目录保留。

## [ERR-20261006-007] description_feedback_directory_rename

**Logged**: 2026-10-06
**Priority**: medium
**Status**: resolved
**Area**: infra

本地登记旧反馈的临时目录 rename 遇到 Windows WinError 5；旧报告、反馈、数据库与账本未改。改用新命名空间独占创建，先原字节写报告再写反馈，不覆盖已有文件、不修改ACL。后续 reader 核验与真实桌面/手机检查通过。失败暂存目录保留为 ignored，无递归删除。见 sprint-detail-feedback-surface.md。See Also: ERR-20261004-001。

## [ERR-20261006-008] guessed_patch_context_recurs

**Logged**: 2026-10-06
**Priority**: medium
**Status**: resolved
**Area**: workflow

批量 apply_patch 再次夹带未经读取的 Markdown 标题上下文，导致整批原子校验失败、没有落盘。随后先 rg 读取准确标题，按实际短上下文分批成功。即便只想占位，也不能向 patch 加未经验证的 hunk；格式或文档尾部猜测同样适用。此错误消耗额度，后续禁止无效占位补丁。

## [ERR-20261006-006] isolated_runtime_bytecode_drift_recurs

**Logged**: 2026-10-06
**Priority**: medium
**Status**: resolved
**Area**: infra

只读评审的Decimal小样本裸Python调用再次改写10个stdlib .pyc，完整verify在receipt检查停止。仅.pyc漂移，源码/EXE/DLL未变；从核对toolchain.json SHA的本地缓存Python tar归档逐文件恢复原receipt哈希，receipt不改。env.ps1+ -B要求同样适用于所有只读worker/临时样本。后续init/fullverify通过1184/1skip。See Also: ERR-20261004-002。

## [ERR-20261006-005] standalone_pytest_basetemp_parent

**Logged**: 2026-10-06
**Priority**: low
**Status**: resolved
**Area**: tests

### Summary

定向pytest指定嵌套basetemp时未先创建父目录，75个fixture报WinError3。预建.cache/pytest-detail-workspace与cache后重跑；沿用verify.ps1的独立临时目录流程，勿将此误报产品回归。


## 2026-10-06: 付费素材传输需明确具体目的地

自动审批拒绝run-pilot.py的首次执行：可信用户回复只明确候选/¥4.04预算，未明确允许将本地画面传往DeepSeek。拒绝发生在CreateProcess前，0请求。向用户原样解释目的地/数据范围缺口并询问共6张注册画面、帧ID、提示词/参数发送至https://api.deepseek.com/chat/completions；用户明确允许后才按同一命令执行，2次成功，无retry。后续预算审批应在一次问题中同时包含具体目的地、数据范围、次数和费用上限，不用间接脚本绕过拒绝。

## 2026-10-06: GitHub推送连接失败

用户已授权推送codex/visual-details；3b09081正常push在GitHub443连接阶段超时，未成功更新远端。保留23d8422/3b09081本地检查点和任务交接，不将本地提交称为已同步；完成离线开发后用命令级HTTP/1.1正常重试并独立核对refs，不改全局网络配置或强推。

本轮apply_patch多次因末尾混入未核对的占位上下文被原子拒绝，无文件改写。修正为只提交已读取的具体上下文；追加新记录先读取标题，不在批量补丁中保留待填写的hunk。

## 2026-10-05: 组合本地提交与远端push被自动审批拒绝

自动审核明确允许范围清晰的本地提交，但拒绝同一命令向尚未由可信用户内容明确授权的origin推送；整个命令未执行。继续单独保存本地检查点并报告远端未同步，最终请求具体分支/目标授权。不得通过工具切换或间接执行绕过外传拒绝。

后续用户明确允许仅推送codex/visual-details到GitHub既有仓库，普通push成功上传00f2796；紧随ls-remote再次出现443连接超时，推送确认与独立查询结果需分别记录，不把查询失败误报为推送未成功。

## 2026-10-05: 交接哈希应与已保存源码和真实对象复算

生产读取断言沿用旧sprint的requestHash `6e9ee8...` 后失败。只读加载同一个V6事件，用继承检查点16f727f的精分析模块和当前模块分别计算，canonical request逐字段相同，两者hash均为 `229a8bcb9bee1f017854108751d89840f458040fd14cdd3490e5c2fd56d00279`；旧文档值无法复现。修正文档/断言，不改源事件或hash算法。比较证据保存在ignored artifacts/detail-inspection-validation/request-identity-comparison.json。

## 2026-10-05: 精分析的窄身份合同不能破坏旧检查数据

本轮首个检查集成回归出现 19 failed/69 passed/1权限skip（18.42s）：新 fixture 使用 schema1，SQLite 按旧合同省略 base prompt hash，不能假设其会持久化；旧检查 fixture 的事件/证据短 ID 也不符合 actor-details-v1 的局部身份格式。修复方向是新侧车 fixture 显式 schema2/价格身份，旧数据缺精分析身份时返回 unsupported/unverified，保留原展示/检索/篮子，不能改写旧 ID 或放松 domain 合同。后续复测结果见 sprint-detail-inspection。

## 2026-10-05: 沙箱里的 asyncio 回环初始化可能挂起

本轮定向 pytest 在第三项停住，`faulthandler_timeout=20` 定位到 `socket._fallback_socketpair -> accept -> asyncio.ProactorEventLoop`，尚未执行检索逻辑。中断本工具启动的两次测试后，允许本机回环的升级调用 15 passed/0skip（0.75s）；没有真实 Provider 请求。后续 HTTP/浏览器/asyncio 验证使用相同授权，不能通过改产品事件循环或放松测试绕过。初始源码定位沿用 docs 中 `ui/` 简写造成路径缺失；实际路径为 `src/gamingcreator/ui/`，应先用 `rg --files` 定位后读取。

## 2026-10-05: Wait for the selected run, and preserve the workspace CSP

The first real V6 browser report captured the loading option as defaultRunId because it only waited for a nonempty select. The validator now waits for an enabled run/search and populated timeline; the repeated report and fresh production browser both confirmed the V6 default. An ad hoc diagnostic used Playwright wait_for_function and hit unsafe-eval CSP rejection; use the established debugger-evaluate polling helper rather than weakening CSP. Launching the user's browser from the filesystem sandbox failed with Access denied; the authorized escalated Start-Workspace.cmd reused the same owned local service and succeeded. GitHub push still timed out after21s; save local commits and record pending remote synchronization.

## 2026-10-05: Persist worker state before usage exhaustion and distinguish valid segments

The V6 worker exhausted its usage allowance before sending a final report/commit. Its isolated worktree already contained implementation, tests and a sprint note; a fresh worker can continue those exact files rather than restarting. Root checkpoints must include resumable unfinished changes and a concise current HANDOFF, not stacks of contradictory current-status paragraphs. Real V5 twice produced identical start/end clocks in window31.5–35.5; strict rejection is correct. Do not relax the parser or repeatedly spend on the same frozen prompt; qualify multi-frame actions before adding visual detail in a separately fingerprinted revision.

## 2026-10-05: Windows port zero may allocate a browser-restricted port

Merged browser regression failed at page.goto with ERR_UNSAFE_PORT on127.0.0.1:1723; no application JavaScript ran. The shared test fixture now directly reserves a random free port in20000–59999, with bounded collision retries, instead of relying on port0. This only changes isolated test listeners, not Windows configuration. Root verification must rerun; do not claim the initial170passed/1skip/1failure as complete. GitHub push also failed with443connection timeout; local commits are durable, remote synchronization requires a later retry.

## 2026-10-04: Prepare nested pytest directories and deterministic stat fixtures

Resumption targeted pytest used a new nested basetemp whose parent did not exist; create the task-specific parent before running, without deleting another session's cache. A pre-existing same-size mutation test also retained identical mtime on this filesystem; explicitly change only the fixture's mtime to test stat invalidation. Production media cache intentionally relies on stat changes; unchanged metadata is a known limit, not proof of immutable bytes. Grok's v3 schema failure has no raw response, so exact malformed boundary remains unknown; use new versioned frame-alias boundaries and limited numeric diagnostics rather than inventing a cause.

## 2026-10-04: Temporal configuration must be accepted consistently

Initial temporal resumption test failed at storage.invalid_config: the input reader allowed nine-frame v3 but SQLite's independent typed allowlist still limited five and required a prompt hash. Aligned only the new version's constraints and supplied the fixture identity; 39 targeted tests then passed. Use unique pytest cache as well as basetemp to avoid other Windows sessions' locked cache. Diagnostic JPEG extraction also requires explicit full-range pixel format; use the existing media service for production rather than ad hoc FFmpeg flags. No global cache/permissions changes were made.

## 2026-10-04: 排序验收绑定错误的播放片段（已修复）

新增源时间排序后，英文浏览器测试仍把JSON导出第一条当作刚播放的检索第一名，区间断言失败。两种排序是不同合同；测试改为找到实际rank1，保持JSON/CSV的源时间升序断言，随后中英文均通过。暂停待完成play会触发AbortError，UI忽略这种主动中断，避免假故障提示。相关文件：scripts/validate-inspection-ui.py、ui/static/app.js；证据sprint-workspace-usability.md。多文件patch须匹配当前整行文本，不能沿用旧CSS/段落上下文；失败时先确认未部分写入再修补。

Command failures and integration errors.

---

## [ERR-20261004-001] pytest_cache_winerror_5

**Logged**: 2026-10-04T02:49:00+08:00
**Priority**: medium
**Status**: resolved
**Area**: tests

### Summary
Default pytest cache directory `.cache/pytest` fails with WinError 5 on this machine.

### Error
```
PermissionError: [WinError 5] 拒绝访问。: .cache/pytest/v/cache
FileExistsError: [WinError 183] when creating that directory
```
With `pytest -W error`, the cache warning becomes a session error and hides real results.

### Context
- Command: `python -m pytest -W error` using `cache_dir` from `pyproject.toml`
- Happened twice on 2026-10-04 while running ASR and vision tests
- Workaround that passed: `-p no:cacheprovider --override-ini=addopts= --basetemp=.cache/pytest-grok-tmp` plus `-W "ignore:Unknown config option:pytest.PytestConfigWarning"`

### Suggested Fix
Keep using the cache-disabled command until `.cache/pytest` can be removed by a process that is not holding it. Do not treat the cache error as a product test failure.

### Metadata
- Reproducible: yes
- Related Files: pyproject.toml
- See Also: ERR-20261004-003

### Resolution
- **Resolved**: 2026-10-04T05:10:00+08:00
- **Commit/PR**: uncommitted
- **Notes**: `cache_dir` is `.cache/pytest-cache`. The locked `.cache/pytest` tree was not deleted. Official `./scripts/verify.ps1` then passed with the cache plugin enabled. Not promoted to AGENTS.md; the machine-specific warning is in HANDOFF.md item 4.

---

## [ERR-20261004-002] toolchain_pyc_receipt

**Logged**: 2026-10-04T03:40:00+08:00
**Priority**: high
**Status**: resolved
**Area**: infra

### Summary
`./scripts/verify.ps1` stopped before tests because 135 pinned stdlib `.pyc` files no longer matched `.tools/toolchain-receipt.json`.

### Error
```
Project Python runtime hash differs from the installation receipt.
```
All 135 mismatches were `__pycache__/*.pyc`. No `.py`, `.exe`, or `.dll` differed.

### Context
- `scripts/env.ps1` sets `PYTHONPYCACHEPREFIX` so project scripts write bytecode under `.cache/pycache`.
- Running `.venv\Scripts\python.exe` without that variable rewrites `.pyc` files inside `.tools/python` and breaks the next receipt check.
- Restored the drifted files from `.cache/uv/downloads/cpython-3.13.16-20261001-windows-x64.tar.gz` after checking its SHA256 against `toolchain.json`. The receipt was not edited.

### Suggested Fix
`scripts/env.ps1` now sets `PYTHONDONTWRITEBYTECODE=1` for project scripts. `PYTHONPYCACHEPREFIX` alone still left the pinned `.pyc` files writable. Do not update the receipt. Direct `.venv\Scripts\python.exe` without `env.ps1` can drift them again; restore from the pinned archive.

### Metadata
- Reproducible: yes
- Related Files: scripts/env.ps1, scripts/toolchain.ps1, .tools/toolchain-receipt.json
- See Also: ERR-20261004-001

### Resolution
- **Resolved**: 2026-10-04T05:10:00+08:00
- **Commit/PR**: uncommitted
- **Notes**: `scripts/env.ps1` sets `PYTHONDONTWRITEBYTECODE=1`. `./scripts/verify.ps1` passed its receipt check on 2026-10-04. The receipt file was not edited.

---

## [ERR-20261004-003] pytest_basetemp_winerror_5

**Logged**: 2026-10-04T04:20:00+08:00
**Priority**: high
**Status**: resolved
**Area**: tests

### Summary
`./scripts/verify.ps1` passed Ruff and mypy, then pytest `-W error` failed while removing `.cache/pytest-tmp`.

### Error
```
117 passed, 211 errors in 19.42s
PermissionError: [WinError 5] 拒绝访问。: '\\?\G:\Tools\ChatGPTRepo\GameingCreatorAgent\.cache\pytest-tmp'
Project check failed: -m pytest -W error
```

### Context
- `pyproject.toml` `addopts` used `--basetemp=.cache/pytest-tmp`.
- `Get-Item` can see the directory. `Get-ChildItem` and `Remove-Item` are access denied. The current user is not an administrator, so takeown was not retried.
- A sibling `.cache/pytest-tmp-run` was created, written, and deleted by the same user.
- Offline wheel builds did not run. This is the same permission family as ERR-20261004-001, on a different path.

### Suggested Fix
Point `--basetemp` at `.cache/pytest-tmp-run`. Do not point it back at `.cache/pytest-tmp`. Rerun `./scripts/verify.ps1` from the repository root after `scripts/env.ps1` is loaded. Do not edit the toolchain receipt.

### Metadata
- Reproducible: yes
- Related Files: pyproject.toml, scripts/verify.ps1
- See Also: ERR-20261004-001

### Resolution
- **Resolved**: 2026-10-04T05:10:00+08:00
- **Commit/PR**: uncommitted
- **Notes**: `addopts` now uses `--basetemp=.cache/pytest-tmp-run`. That directory can be created and deleted by the current user. `./scripts/verify.ps1` then exited 0. `.cache/pytest-tmp` remains locked. Not promoted to AGENTS.md.

---

## [ERR-20261004-004] embedding_cache_replace_winerror_5

**Logged**: 2026-10-04T12:50:00+08:00
**Priority**: high
**Status**: resolved
**Area**: infra

### Summary
Hybrid demo search failed with `embedding.response_invalid` because replacing a stale `.cache/embeddings/*.json` raised WinError 5.

### Error
```
PermissionError: [WinError 5] 拒绝访问。
.cache/embeddings/write-*/vector.json -> .cache/embeddings/<hash>.json
```

### Context
- The computed vector was valid. The failure happened only while writing the cache.
- Same permission family as ERR-20261004-001. The current user cannot delete the locked file.

### Suggested Fix
Ignore `OSError` from the cache write and return the verified vector. Do not delete the locked file with takeown.

### Metadata
- Reproducible: yes
- Related Files: src/gamingcreator/infrastructure/local_embeddings.py
- See Also: ERR-20261004-001

### Resolution
- **Resolved**: 2026-10-04T13:05:00+08:00
- **Commit/PR**: uncommitted
- **Notes**: `embed` now keeps the vector when the cache file cannot be replaced. The demo search then completed. Not promoted to AGENTS.md.

---
