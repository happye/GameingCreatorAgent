# Sprint：冻结时自动盘点登记来源

更新：2026-10-24，Phase 0，main，Claude Code本机会话。主线：F006来源独立性的用户流程简化（接[freeze-v2](sprint-freeze-source-inventory.md)与[黑边／镜像](sprint-inventory-crop-mirror.md)）。无新录像／图片／付费API，不分配录制组。

## 为什么做

benchmark-freeze-v2要求盘点报告，否则阻断`source_inventory_missing`。目前用户须先在PowerShell单独运行`inventory-sources.ps1`再上传报告；用户本机只有Windows PowerShell 5.1，工作台才是主要入口。冻结时自动盘点计划内来源，可让用户在工作台一次冻结就得到明确的共用画面阻断，改分组后再冻结。

## 合同

文件归属（单一写者）：`src/gamingcreator/cli/main.py`（仅freeze-benchmark参数与`execute_freeze_benchmark`）、`scripts/prepare-benchmark.ps1`、`src/gamingcreator/ui/benchmark_workflow.py`、`src/gamingcreator/ui/static/benchmark-workflow.js`、`tests/test_benchmark_preparation.py`或新`tests/test_freeze_auto_inventory.py`、`tests/test_benchmark_workflow.py`、`tests/test_benchmark_workflow_browser.py`、`docs/references/benchmark-preparation-guide.md`、`docs/references/source-inventory-guide.md`。不改`benchmark_preparation.py`／`benchmark_preparation_files.py`／`benchmark_inventory_binding.py`的规则（自动报告与上传报告走同一冻结路径）。

1. CLI：`freeze-benchmark --auto-inventory`，与`--inventory`互斥（同时给出→输入错误）。启用时对计划中全部来源（与冻结相同的路径解析：相对路径按计划文件目录，`resolve()`后）调用现有`build_source_inventory`（`FfmpegMediaProcessor`＋`FfmpegSignatureExtractor`），以与`inventory-sources`输出完全相同的序列化得到报告字节，再作为inventory传给现有`freeze_document_v2`／`write_freeze`。报告只存在冻结包内（`source-inventory.json`），不写入素材目录。结果JSON的`sourceInventory`摘要增加`"generated": "auto"|"provided"|null`。
2. PowerShell：`prepare-benchmark.ps1 -AutoInventory`（开关，仅Freeze，与`-InventoryPath`互斥）。
3. 工作台冻结步骤：未上传报告时提供复选框“冻结时自动盘点登记的录像（本机，不花钱，较长素材需几分钟）”，默认勾选；勾选即提交`autoInventory: "true"`字段（字段集校验相应放宽，仅freeze步骤；旧客户端只传`inputText`或空字段继续有效）。上传报告与自动盘点互斥。页面显示所用来源（上传／自动／未提供）。
4. 失败处理：盘点中单个来源失败按现有报告规则记入`failedSources`，冻结照常完成并由`source_inventory_incomplete`阻断；不因盘点失败而写出不完整冻结包。
5. 测试：合成lavfi素材计划（两个来源，其中一个为另一的派生片且分到不同录制组）`--auto-inventory`冻结得到`shared_footage_has_different_recording_groups`；同组无该阻断；互斥参数报错；工作台HTTP冻结步骤带`autoInventory`成功、与上传同时给出被拒；浏览器测试复选框默认勾选并显示“自动”。自动生成的冻结包`read_freeze`可读、篡改仍拒绝。

## 验收

定向测试（-W error）、`ruff check src tests`、`ruff format --check`、`mypy`全部通过；主控在本机用Atom异组反例计划`-AutoInventory`实跑得到阻断；5个已存冻结读取与SHA不变。独立评估gc-reviewer。

## 结果

- 实现：gc-coder（请求sonnet）在隔离worktree分支提交89427ae，主控快进合入main；worktree里指向主仓库`.tools`的目录链接先单独删除再清理目录，随后工具链完整性检查通过。
- 评估：gc-reviewer（请求sonnet，只读）PASS。确认共享序列化不改变其他JSON写出字节、临时目录随上下文管理器删除（env下位于`.cache/tmp`）、整个盘点工具失败不留冻结包、字段校验与互斥有效。低严重度：状态行`inventorySource`为列表／字典时抛TypeError而非“记录已改变”，主控已改为元组成员判断并补3个用例；脚本互斥与临时目录删除无自动化测试（已手工核实）。
- 真实验证：Atom异组反例计划`prepare-benchmark.ps1 -AutoInventory`12.3秒冻结，自动盘点2个来源、1对共用画面，得到`shared_footage_has_different_recording_groups`，`generated: auto`，包内含`source-inventory.json`；5个已存冻结读取与SHA不变。
- 验证：定向8文件214项通过（-W error），工作台40项（含新3例）通过，ruff／mypy全仓干净，脚本PowerShell 5.1解析0错误。同日合入前完整verify：3517 passed／1 failed（TD012既有WinError10053）／3 skipped，未挂起。
