# DSH协作：验收步骤完成状态可靠读取

2026-10-23，Phase 0／TD014。本轮主要交付：验收流程步骤保存完成后，查询不再因读取旧快照而误报“中断”；真正丢失执行所有权的running仍显示中断。服务于后续冻结／绑定／固定候选流程，不新增诊断页、不改变质量判定。

## 合同与分工

Codex主控形成合同、执行定向测试、验收并写公共记录／Git；原生DSH唯一写`src/gamingcreator/ui/benchmark_workflow.py`和`tests/test_benchmark_workflow.py`。Luna/high只读定位已完成，唯一Sol/high负责并发／持久化边界独立评估，不再叠加普通reviewer。DSH不是唯一贡献者，不改其他源码或撤销他人编辑；无其他源码写者，无递归委派。

已确认路径：get先读running → worker写finished并关闭OS锁 → get取得空闲结果却把旧running投影成interrupted。修复要求在观察可用锁后读新鲜磁盘状态，读完前保持一致的所有权判断；维持非阻塞操作、真实writer排他、异常传播和只读历史。不得以sleep／重试／自动续跑或后台改写记录掩盖竞态，禁止伪造finished。

新增确定性交错回归，覆盖完成／失败终态、真实中断、活跃所有权与异常锁释放；保留现有HTTP原片流程、重载、显式重试及完整资格保护。主控仅在源码冻结后运行相关测试和静态检查；DSH不运行pytest或verify，不下载／安装依赖。

保护原片、分析、费用、原标注及已有验收资料，不启动任何录像API／补窗／旧launcher，不改变F006/F009/F010false。只允许当前显式skill授权下必要的DSH开发模型调用，单列原生用量，不宣称费用硬上限或协作免费。

## 恢复与当前节点

Git基线main `e19aa2f`，工作树起始干净，当前scaffold及完整环境检查通过。先recover旧任务确认两请求均COMPLETED／无未决，再为本轮新交付建立新task；不沿已提交后的旧合同派发。

同目录专属workspace `f4395711-a8fb-49a3-ad95-7305ce9ea1e8`；新task `gamingcreator-acceptance-state-20261023`；session `codex-5679568d-88be-45a9-ba51-fe2f4a11bacc`。connection native；账本`C:/Users/Crux/.codex/codex-dsh-state`。旧已交付task `gamingcreator-workspace-phase0-20261022`保留，不重投。

最终状态：一个实施请求已完成，主控29项回归及Ruff／格式／mypy通过、唯一独立评估R1–R6 PASS，86旧文件摘要不变。两回执均已重读验证，合入前源码身份已保存。完整证据与边界见[报告](report-2026-10-23-acceptance-state.md)。下一核TD006回看源时间边界，禁止重投本轮已完成请求。真实检索质量、代表素材／人评仍依原[计划](phase-0-plan.md)及[人工待办](human-inputs.md)，本修复不解除它们，也不要求重复标注。
