# Phase 0 对原保存排名计算人工评分

2026-10-07，root / Codex，codex/visual-details，接12a7614。上一候选评审已交付；完整两旧Windows环境失败一次窄复查通过，TD012保留，不重复无变化检查。旧worker／worktree冻结，本轮顺序单owner。

F006主要交付：显式-Score导入人工记录后，读取已核对的原十位排名，以原benchmark算法计算质量，不再搜索。缺位／结构重复／同真实动作／失败查询、主稀疏负例和未判定保持原规则。原检索身份／时长和原分析费用可追溯，计分耗时单独显示，不能把读回的微秒算作检索速度；来源和费用未知不自动通过。

root独占application/benchmark_review_scoring.py／benchmark_analysis_costs.py、新固定计分测试；修改现有prepare-benchmark-review.py／ps1加入显式Score，cli/main.py复用原基础费用汇总，公共记录／指南。Application纯运算，无新Provider／DB／HTTP／模型调用；script既有准备函数只读来源和保存检索。输出新目录并保留原输入与最后回执，未过或未验证退出6但保留报告。旧未Score准备／导入行为保留。

验证合成7/10、少例／负例、独立不足／标签不足、已知及人工映射重复／缺位、原失败不变成功、音频身份、原时间／费用unknown与输入篡改；脚本禁止搜索／模型／预算下实际SQLite归档。真实三开发素材用上一空记录和原报告，0新增普通检索／模型／预算／真评分，第二进程回读报告。源字节／旧unknown／新proposal原SHA及F006/F009/F010false保持。

本轮已向用户说明直接对已回看原排名计分的用途，继续既定Phase 0路径。网络上一普通push21秒连接失败，此轮先离线交付，不循环联网；新两次¥4.07仍待授权，原旧预算不扩张。

## 实现与当前证据

原算法不改；新纯评分模块从原十位投影BenchmarkHit，原失败明确抛出并保留failed，缺位与结构重复不补位；原人工事件去重／未判定仍旧。显式--score／-Score要求记录，null／false退出6前独占发布benchmark-fixed-report.json。原检索时间／ID保持，scoredAt／scoringElapsedMs独立；原报告SHA与日期／时长／耗时比例核对。基础费用抽取为纯benchmark_analysis_costs，CLI原正常／缺来源行为复用，评分以store核对原attempt汇总为准，编辑报告cost不能让unknown过gate。

24新增行为及相关116定向通过3.53s；一次完整2095passed／1 Windows symlink权限skip340.95s，156格式／81类型／lint／CLI／双离线wheel SHA66f89fdbd5946575545068693971f95a5f21a872aad925210c02bee030c8552e通过，80包文件同源码、无媒体／缓存／DB。JUnit2096／0fail／0error／1权限skip及package回执在.cache/benchmark-fixed-score-*，进程已结束。首次收集误猜snapshot模块直接修正，一处篡改测试误用共享template而非独立记录，deepcopy后正确拒绝，合同未放松。上一TD012本次未重现但原因仍未解决，不循环诊断；后续仅文档／ignored证据，不重复全套。

实际三开发素材复用上一原报告／空记录：禁搜索／persist／模型／HTTP／预算构造下直接465ms；公开PowerShell7中文-Score新目录1018ms，均exit6保留报告，原三十slots／三retrievalId／费用／原检索1512.274ms逐项一致，纯计分0.072ms不当速度提升。第二进程同三查询／三十位／SHA，项目832文件含DB逐字节保持、三源SHA保持，普通检索214→214，0新Provider／预算／真评分；proposal原SHA保持。ignored artifacts/benchmark-fixed-scoring-validation/check-fixed-score.py／report.json／原排名计分／公开入口计分为证据。

已向用户详细汇报固定三十位置／原身份保持、214→214零新增搜索、约1秒公开入口与第二进程一致、空记录未验证／缺位重复协议，以及原文件和费用边界；完整结果与交付报告已保存。下一主要交付多段原录像批量离线准备，一次处理清单、独立保存每个素材任务及恢复状态，不进行模型分析；保存本地提交后登记范围，不把工具输出当独立人评或越过正式桌面门槛。本轮0push／远端读取，上次21秒连接失败后不循环联网；发布事实见Git及.cache/benchmark-fixed-score-publication.json。
