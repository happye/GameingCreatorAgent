# Sprint：工作台状态文件并发替换修复（TD012子项）

更新：2026-10-24，Phase 0，main，Claude Code本机会话（主控claude-opus-5-5）。单Agent实现＋独立评估，无新录像／图片／付费API。

## 目标与范围

修复TD006回归中复现、阻断工作台继续使用的两项失败：登记步骤完成后显示interrupted、HTTP参考导入轮询返回缺busy；同根因的素材批量准备state.json检查点失败一并修复。只改`ui/benchmark_workflow.py`、`infrastructure/media_batch_files.py`及对应测试；不改保存格式、执行锁语义、费用或验收逻辑，不加生产重试。

## 根因（已实证）

本机临时脚本复现：Windows上对一个正被其他线程打开的文件执行`Path.replace`抛`PermissionError [WinError 5]`；反过来在替换进行中打开该文件也会抛OSError。

- 验收流程：后台线程结束时替换`status.json`不在`self._lock`内，而网页轮询`get()`／`file()`／`binding_options()`同时读取。替换失败→状态停在running→锁释放后被正确投影为interrupted（失败关闭，不是误报完成）；读取失败→HTTP把OSError转成400错误体，没有busy字段。
- 素材批量：任务线程每项完成后替换`state.json`，界面`catalog()`／续跑读取同一文件且无共享锁；替换失败被包装成`storage.batch_checkpoint`并停止本次准备，解释TD012中多次“本次准备停止”。

## 修复

- `BenchmarkWorkflows._attempts`读取每个status.json与`_run`终态写入共用同一进程内RLock；ProjectWriterLock仍为非阻塞，终态先落盘再释放OS锁的TD014顺序不变。
- `media_batch_files`新增进程级`_STATE_IO`锁，覆盖state.json读取与检查点替换。

## 验证

- 新增确定性测试3项：`test_terminal_write_waits_for_an_open_status_read`、`test_status_query_waits_for_the_terminal_write`、`test_checkpoint_waits_for_an_open_state_read`。去掉修复时分别以WinError5／running快照／storage.batch_checkpoint失败，修复后通过。
- 工作台扩展组10个测试文件（验收流程、原片参考、版本选择、素材准备／批次及其浏览器测试）按`scripts/env.ps1`环境一次运行：129项129通过、0失败、88.5秒，JUnit `.cache/td012-extended-final.xml`。Ruff格式／检查与两源码mypy通过。
- 同组还暴露一项既有过时断言：`test_workspace_flow_forms_playback_download_import_and_reload`期望总状态以“检索质量尚未验证”结尾，但ce934e0有意追加“验收就绪只是资格汇总，不等于已验收或F006通过。”。在未修改HEAD上同样失败；已改测试同时断言两段文字，页面不变。
- 独立评估：code-quality-guard角色（工作流子Agent，请求opus／high；本会话启动时`.claude/agents`尚未存在，按回退方式传角色正文）PASS，无P0／P1；其建议的测试注释与文档同步已完成。另一只读扫描（请求sonnet）列出其余temp+replace站点，仅批量state.json为同进程确认竞态。型号为请求值，未从转录核实。
- 未做：整仓`./scripts/verify.ps1`未重跑。

## 遗留（仍归TD012）

- 跨进程打开文件（杀毒／索引器、编辑器、同仓库第二个工作台进程）仍可能使替换失败，表现为失败关闭（interrupted／检查点失败），不损坏数据；如再现再评估对WinError5／32的有界重试。
- `scripts/validate-temporal-gameplay.py`固定名`report.json.tmp`反复改写导致的report.json WinError5（视觉细节试验测试）不是同进程竞态，未改。
- TD012中的WinError10053本机HTTP连接中断与其他未复现项未处理。
