# Sprint：恢复正式检查门禁（TD015）与联合检索回归（TD016）

更新：2026-10-24，Phase 0，main，Claude Code本机会话，主控单Agent。无新录像／图片／付费API。

## 起因

做素材盘点时发现main上`./scripts/verify.ps1`静态门禁不通过；修完后首次全量又在约20%处无限挂起（用户看到“卡在20%”）。逐项定位后发现几处真实问题，最重要的是一个已交付功能的回归。

## 发现与处理

1. 静态门禁（2026-10-22提交引入）：ruff安全自动修复42项＋格式化29文件；两处测试无用变量删除；mypy 50项均为JSON `object`未先收窄，改为“先取变量再判断同一变量”或显式标注，不改运行行为。
2. 全量挂起：`test_detail_budget_sidecar::test_overlapping_sends_recheck_the_open_attempt_inside_the_lock`第一个发送在调用模型前被10-22新增的精分析请求合同拒绝，`entered`事件永不出现，测试在`await entered.wait()`无限等待。根因是共享夹具媒体编号`media-1`与媒体SHA不一致；真实流程中media_id就是SHA256。夹具改为`MEDIA = "b"*64`后，该文件及8个复用夹具的文件（约60项费用确认／预算／恢复测试）恢复通过。只读用当前合同核验仓库内6条真实精分析请求与结果全部通过，确认10-22规则不影响真实费用记录读回。
3. **TD016联合检索回归（真实可复现）**：`search-project`在hybrid／semantic下（含`-DetailProfile`“已有细节”）保存时报“单任务检索投影hybrid／semantic缺少embedding”。`cli/main.py`为渲染每个录像的候选行临时构造`SearchResult`，没有带联合检索的embedding身份与阈值，10-22后`_search_document`对整份文档做合同检查而拒绝。已把`result.embedding_metadata`、`min_similarity`、`min_semantic_margin`传入；真实demo-phase0上`search-project -DetailProfile v5`成功返回前10候选并保存。
4. 三个含中文的PowerShell脚本（`search-project.ps1`、`confirm-detail-billing.ps1`、`test-media-spike.ps1`）是无BOM的UTF-8，用户本机只有Windows PowerShell 5.1（无PowerShell 7），会按GBK解析而语法错误；已加UTF-8 BOM，5.1解析器0错误并实跑。
5. 过时测试：健康检查能力列表补10-22新增三项；“篡改来源被拒绝”测试此前只是因测试自身改searchId未同步recordPath而被`retrieval.contract`拒绝，并未测到篡改本身，已同步recordPath，现每种篡改由`retrieval.detail_snapshot`拒绝（22项通过）。
6. 读取真实demo库的两个测试文件共33处`SqliteTimelineStore.open`从不关闭，`-W error`下泄漏被算到后续任意测试；加文件内`_open`登记与autouse关闭。生产代码有正常`close()`，非生产泄漏。
7. 环境：本会话早先未带`-B`运行Python重写了48个标准库pyc，导致工具链回执校验失败；已从哈希核对的官方压缩包逐个恢复（只动这48个文件），并在记忆中固化“一律-B”。

## 验证

- 静态：`ruff check src tests`、`ruff format --check`（249文件）、`mypy`（118源文件）全部通过。
- 完整`verify.ps1`（不重定向、`PYTHONDONTWRITEBYTECODE=1`）：3440 passed／4 failed／3 skipped，18分32秒，不再挂起。4项中sqlite泄漏已修（相邻文件81项复跑仅剩一项TD012偶发）；其余3项为TD012偶发：`test_media_preparation_jobs`单独连跑3次均20/20，两个浏览器计时测试单独重跑5/5通过。修完后未再跑第四次完整verify。
- 真实入口：`run-demo.ps1 -Run`hybrid检索、`search-project.ps1 -DetailProfile v5`均成功；6条真实精分析记录合同核验通过。
