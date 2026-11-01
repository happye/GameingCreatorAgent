# 验收步骤不再把刚完成误报为中断

2026-10-23，Phase 0／TD014工程修复完成。原片参考、冻结等后台步骤刚好完成时，刷新／轮询现在会返回已保存的完成或失败终态；真正失去执行所有权的running仍显示中断。用户无需因为错误中断提示重新提交资料。

## 原因与修复

原get先读running快照，再探测OS锁；worker在两者之间写入终态并释放锁时，get错误地把旧快照投影成interrupted。新`_fresh_attempts`非阻塞取得空闲锁后，持锁读取新鲜磁盘快照，所有路径关闭自己的观察锁。锁忙保持busy，其余路径／存储错误传播；失去所有权的running只在返回内存投影为中断，不改磁盘、不重跑步骤。

读取后是独立解码的dict快照，旧attempt不会被重新执行，释放锁后纯内存判断安全；后续新步骤不改变已有attempt身份。状态响应代表读取当时快照，不承诺返回时外部仍无新步骤。流程级锁对历史孤儿保持原保守忙状态。

生产仅修改`src/gamingcreator/ui/benchmark_workflow.py`，测试仅修改`tests/test_benchmark_workflow.py`。未改变UI/API schema、评分、完整资格、原标注、费用或模型调用路径。

## 协作与验证

沿用同项目目录独立workspace `f4395711-a8fb-49a3-ad95-7305ce9ea1e8`，新task `gamingcreator-acceptance-state-20261023`／session `codex-5679568d-88be-45a9-ba51-fe2f4a11bacc`。旧任务先recover确认已完成且无未决；本轮一个实施请求`3d9d699c-444a-4d61-9ddb-b3830e6e8ec7`已COMPLETED，断开后未重投。完整答复及真实diff均已读取。

原生DSH唯一源码写者；Codex主控合同／测试／集成；Luna/high只读定位，唯一Sol/high独立评估R1–R6最终PASS，无重复reviewer。实际型号／推理已从运行metadata核实并保存，不依据自报。

主控按rev2合同`317ca2b030424723ff27e4ffb9dade245e32642c4d6a0c39614cc589cd9f9f40`运行并重读两回执，均`valid/evidenceComplete/passed=true`、退出0。执行前后sourceFingerprint一致：`e13524475eb4be3c8913928cdf5dbd289c25e97dd204c2ba1cab9dbe7fe9b98c`。

| 检查 | 实际结果 | run ID |
| --- | --- | --- |
| workflow与run_selection相关回归 | 29通过，0失败／错误／跳过；16.05秒 | `5b313f0a-c536-4cea-9ec5-1400a21fa38e` |
| 两文件Ruff／格式，workflow模块mypy | 全部通过 | `0312d686-b930-4682-991d-ad3aae69345e` |
| 已有验收资料 | 86份JSON/HTML摘要不变 | 实施前清单与实施后独立核对 |

新用例用真实OS锁及可控acquire交错，在旧running读出后精确写finished／failed并释放所有权，证明不会再用旧快照；读取异常释放锁、非busy锁错误传播及原真实中断／活跃写者保护均覆盖。原HTTP原片／参考导入、重载、显式新目录重试、Completed版本选择保持通过。

runner是command；pytest结论来自stdout与JUnit，不声称原生pytest收集器证明。未重复整仓verify／wheel，也未进行新的真实浏览器验收或内容质量判断。TD014关闭的是确证的旧快照误报竞态，不宣称其他存储／HTTP债务或全部历史失败都已解决。

证据位于忽略目录`artifacts/dsh-acceptance-state-20261023/`：合同、原源码、完整prompt、JUnit、stdout／stderr／回执、86文件原摘要、角色metadata及validated-source.json。文档／Git变化前保存测试有效时的源码SHA和Git blob；合入后回执仅作历史，下一新目标不沿旧合同重投。

DSH用量单列`dsh-usage.json`：一个逻辑派发、28条可见用量样本，未缓存输入32826／缓存读8614144／输出44281 tokens；不是提供方账单或费用硬上限。测试计划初次绑定因Git对中文路径输出转义而在执行前拒绝，改用单命令`git -c core.quotepath=false ls-files`；未改全局设置、账本或要求，无测试／模型重投。

## 保留与下一步

本轮没有录像API／发图／补窗／旧launcher／标注操作。长钟馗269成功／3缺口、469观察、旧费用及参考保持，F006/F009/F010仍false；无需重标或再次批准本地开发。下一继续核对原片回看与源时钟的已知TD006边界，先以现有代码和可证输入确认是否确有缺陷；真实检索质量仍沿事前参考／冻结／Completed绑定／固定Top10人评路径，素材依赖不由此自动满足。
