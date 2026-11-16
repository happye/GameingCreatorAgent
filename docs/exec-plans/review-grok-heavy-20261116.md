# Grok A01–F16交付审查（2026-11-16）

结论：有实质新增实现和媒体实例，但仍需返工，暂不建议整批集成。确认5个P2，另有E10复用合同未满足及发布取消边界待验证。本次只审查，没有修改业务代码、提交Grok成果或重跑全量。

## 审查基线与范围

- 工作树：`G:\Tools\ChatGPTRepo\GameingCreatorAgent\.worktrees\grok-studio-20261115`，HEAD `e4e3d22`，交付仍为未提交改动。
- 合同：主树`docs/exec-plans/grok-heavy-development-20261115.md`；最新报告为工作树`.cache/f16-handoff.md`，旧37项报告不是本轮结论。
- A–D由独立reviewer只读核查；E由唯一关键边界guard核查；主代理检查F组产物验证代码并执行定向及对抗复现。下面代码路径均相对此Grok工作树。

## 需要修复

| 编号 | 级别 | 位置 | 触发、影响与最低修复要求 |
| --- | --- | --- | --- |
| R01 | P2 | `infrastructure/asr_words.py:405`、`:478`，`cli/creation_render.py:102` | 显式选择的逐词结果损坏后，投影接口拒绝，但渲染读取把错误吞成None，静默使用段级字幕；调用者无法知道逐词烧录未生效。显式绑定损坏必须报错；仅未绑定或可信空词结果允许降级。补经真实渲染入口拒绝坏sidecar的回归。 |
| R02 | P2 | `ui/asr_words_jobs.py:182`；异常来源`infrastructure/asr_words_sidecar.py:369` | 磁盘满/拒写被转换为ValueError，任务仅捕AppError和CancelledError，线程退出但状态永久running。预期文件错误应转AppError，最外层异常也必须进入failed终态并保留诊断。 |
| R03 | P2 | `ui/static/studio/multitrack.js:127`、`:182` | 拖动中撤销/改音量使token失效时，只清drag状态而未cleanup；之后卸载找不到清理函数，残留window keydown等监听。先幂等清理，再清状态，独立保留活动清理ref；补失效后切页且不再pointerup的场景。已有token门挡住了旧selection落地，不能把本问题夸成旧音轨覆盖。 |
| R04 | P2 | `application/screen_text_reports.py:341`、`:362` | OCR报告仅校schema与帧摘要，摘要不覆盖OCR正文。改lines[].text且保留来源和framesDigest，仍能作为有效搜索结果进入UI与导出。按C01补整体文件hash回执和读取校验；旧无回执报告明确兼容政策，不能把帧hash当正文完整性。 |
| R05 | P2 | `ui/static/screen-text-highlight.js:6`；`application/screen_text_reports.py:187` | 服务端NFKC+casefold，前端NFKC+lowercase；Straße查询STRASSE会命中但无法高亮，final sigma也不一致。统一匹配语义并保持到原始字素位置的映射。 |

R01/R02已由主代理用隔离临时项目和fake worker执行复现，不调用真实模型，不改用户数据。脚本`.cache/scratch/review-grok-20261116.py`的实际输出：

```text
write error escaped
{'status': 'running', 'live': False, 'error': None}
projection rejected asr.words_damaged
explicit corrupted word result: None
```

R03–R05是当前代码调用链证据，本次没有为它们新建运行测试，修复时需补相应行为验证。

## 交付缺口与待验证边界

- **E10没有实现计算前复用。** `infrastructure/asr_words.py:124`先调用模型，再发布/判断已有结果；`tests/test_asr_words_cli.py:233`明确期望第二次后provider.calls==2。当前只复用输出文件，同配置仍重复ASR。应先按来源/音频/clock/model/revision查找并验证既有结果，命中后不再执行模型。
- **发布时取消仍待验证。** `asr_words.py:139`最后检查取消，随后sidecar同步写文件并rename；需要写入屏障复现“取消已经可见后是否仍发布”。本次未将该风险当作已经复现的第6个P2。
- **OCR真实组件3项未实测。** 报告保留了EncodedCommand启动异常，不能把fake/定向通过当成Windows OCR实跑通过。
- **真实实例不等于人评。** E24及F组已有实例记录；不据此提升逐词准确度、七模式创意质量或平台发布验收。

## 测试与全量口径

Grok原全量日志`.cache/test-logs/verify-20261116-031427.log`：**5486 passed、101 skipped、43 failed、1 error**。报告末尾记录了后续定向处理；旧15处render失败是测试桩缺burn_cues参数，当前已处理，不能继续当作15个现存生产回归。架构分层也已有修复。

本次主代理在Grok树中明确带`--override-ini=pythonpath=src`执行：

1. `test_architecture.py`、`test_inspection_http.py::test_verified_media_detects_rewrite_with_restored_times`、`test_creation_revision_jobs.py::test_revision_trim_order_restore_restart_and_source_immutability`：**5 passed**，日志`pytest-20261116-190253.log`。
2. `test_f12_package_damage.py`、`test_f14_publication_field_errors.py`、`test_asr_words_boundaries.py`、`test_asr_words_sidecar.py`、`test_screen_text_reports.py`、`test_proxy_inventory.py`、`test_plan_content_dedup.py`：**50 passed、1 skipped**，日志`pytest-20261116-190341.log`。

两轮各有quiet关闭cacheprovider引出的配置警告，未将其当业务失败；本次没有第二轮全量。上述55项通过不能覆盖R01/R02的异常路径，也不能把原失败全量改记为绿色。

## 接收建议

先修R01–R05及E10，补异常/取消和手势清理回归；保留现有真实产物与已通过证据，定向验证修复和实际受影响功能。修复后再做差分集成，不整文件覆盖主树已交付的v2草稿恢复。原片、旧分析、人工标签、账本和所有工作树成果继续保留。

## 修复追记（2026-11-16）

用户随后授权修复及继续开发。本报告上文是原Grok工作树的审查快照；主树已在独立分支修复R01–R05、E10及发布取消边界，保留原成果。独立关键边界审查又关闭了“未验模型身份先过滤导致重算”和“缺回执v2降为legacy进入局部搜索”两个残口。最终ASR 6c6d236、UI/OCR 04070ce均通过审查，合入主树6771587，v2草稿恢复与编辑代数同时保留。

主树9文件99 passed（`.cache/test-logs/pytest-20261116-200740.log`），覆盖ASR、手势、OCR及原v2草稿恢复；全src/tests Ruff与格式（612文件）、mypy（233源文件）通过。原全量失败节点另行复核，完整全量仍按原失败记录，不重跑全量或冒称全绿。完整修复验收与后续状态见[sprint](sprint-grok-repair-integration.md)。
