# 当前交接

更新时间：2026-10-06（Asia/Hong_Kong）。Codex、Claude Code、Grok Build共用；恢复先核对Git和实际证据。历史见progress.md，各特性验收见feature_list.json。

所有项目Agent持续遵守AGENTS.md和docs/references/agent-workflow.md的通俗详细汇报规则：每次关键改动后说明现在能做什么、使用帮助、真实验证与不足、下一具体动作；跨会话／工具／子任务有效。规则已写入各工具记忆入口，不重复询问。

## 当前成果

分支codex/visual-details；root顺序完成已有录像来源审计及中文动作别称修复，检索bm25-e5-rrf-v7。正向中英文动作仅补既有中文别称：跳跃／跳起／起跳、射击／开枪、战斗／打斗、交互／互动；未追加English jump给中文或jumping，避免JUMP标题成为动作依据。原v6英文边界／NFKC／否认规则保留，否定意图保持原词法行为，不实现一般缺席语义。源事实、passage哈希、缓存身份、候选ID、证据时钟及0.80／0.02阈值不变。

- 四份完成分析、三个视频SHA、260事件：实机54.743220秒Atom同源v4 96b5f01530ce43e2944828fb0520b9b4／40、v6 f601fb9b3e734d5ea188fc15c790acbb／33；64.943220秒Atom PV v2 c6d93b984f374cd4aa755ed0c81e4d73／76；95.175874秒漫画PV v2 f76f5d6495314c04ae04083614d4afd6／111。Atom的不同文件仍可能同录制组，非独立最终验收素材。
- 每侧108词法＋24混合只读审计。起跳实机v4／v6 0→2；交互／interacting在v4 1→3、Atom PVv2 0→4、v6 1→2。97词法和22混合结果／信号逐项不变；旧v4 jumping混合两个原事件顺序改变、跳跃BM25变化，原cosine／源身份不变，不声称全部排序相同。
- 漫画jump五条为90–95秒游戏标题／版权文字，不是动作标签；root最初误报已依据完整原文向用户纠正。跳跃／jumping仍0。四run射击／开枪均无文字支持；漫画发射1／爆炸6不等于射击。Boss复合句部分字词命中不證同一主体全条件成立，质量仍未通过。
- 新39行为反例，定向237 passed（JUnit6.331s）；完整verify **1862 passed／1 Windows文件symlink权限skip，220.13s**，Ruff136／mypy72／CLI／双离线wheel SHA **51c1b484e3c03b211c09f9d47e00dbcbda9ed347036a985c872caf9d4ddb59e6**。包内71项目文件同源码，无素材／缓存／DB；JUnit1863 tests／0 failures／0 errors／1 skip。上一1823为历史基线。
- 首次定向233 passed／4 setup errors由root未建新basetemp父目录触发WinError3，创建独占父目录／cache后全通过，首次JUnit保留。比较脚本原强求混合why全相同已纠正，实际旧v4两原事件排序变化已披露。
- 真实1366／390起跳2／互动2、十槽缺8、下载同当前响应、第二候选实际11.5秒回看／证据、无页面错误／外部请求／横溢通过，root查看双图。第一browser-report.json回看字段残留英文名称写null，实际断言通过；生成器已修，未覆盖原证据。
- 纯审计两个项目全文件／DB／侧车／预算／原查询记录字节不变，0普通搜索。真实浏览器沿普通API追加4次、生产追加1次；基础表／注册视频证据／精分析反馈预算／冻结proposal保持，不能把普通UI测试称整个DB字节不变。
- 生产health／state／CIM／父子exe／完整命令／仓库身份匹配后替换旧51180／46444。最新快照 **61396／parent56740**，新v7／起跳2、旧v2三个确认＋一个纠错、精分析v4缺失及不跨版本反馈重验通过。PID仅快照，任何操作前重新核对，不能盲停。
- 本轮0远程视觉／精分析请求、0预留／新增费用／真实人评。F006/F009/F010 false，人工质量字段为空。已按持续规则汇报作用、实际不足、JUMP误报纠正、验证和下一步。

## 下一工作

1. root顺序登记并检查已有候选的主体／镜头连续性／动作文字依据，区分标题、特效、物体存在与真实动作；实际漏检确认后才改检索，不新增分析，不重试unknown run。
2. F006仍需10–20段代表录像、按原录制会话划分独立测试、事前冻结查询与人工参考事件；主查询至少十个独立可用参考事件，十固定槽至少七个不同事件获人工2/3。开发PV与同视频多版本不能替代独立测试，描述确认不等于检索评级。
3. 网络已恢复，源码／报告6763484a67035fc8aa5f26fb7d595880f5b6afcc已普通push到已授权https://github.com/happye/GameingCreatorAgent的codex/visual-details，独立ls-remote同SHA；此前0ae1a68后的积压提交也已同步。当前仅更新本交接同步记录，最终文档checkpoint及远端核对以.cache/retrieval-corpus-publication.json和Git为准；不更新main／强推，不循环联网或改全局配置。
4. 新精分析v4仍待对应新授权；未答复继续离线，Goal active。额度／网络恢复不构成新增模型许可。完整检查已通过，恢复不要无变化重复验证，先读Git和证据。

## 费用、授权与实际人评

原两次／最高¥4.04／原六帧到DeepSeek授权已全部执行，估价¥0.01850612、新unknown0；全任务已知¥0.24934532、总承诺¥4.31488132。旧unknown预留¥4.065536保留，禁止重试漫画run 0ba106578bc7435c8689d12892a35dfb或换目录清账。

新artifacts/detail-temporal-validation/pilot-proposal.json SHA **06829ab9dc835545ef8c4de5c829351fc686ce70c990d8c902b9b919b2f062c6**。对应新两次／最高¥4.07／同六帧到DeepSeek chat/completions问题未收到答复：executionAuthorized=false、paidRequestsSent=0，新实验未预留。旧预算余量不等于新次数。

用户只确认35–36秒三个描述，拒绝28–29秒s1/a2：近镜头物品遮住人物，它是物品，不是新人物。其他描述、属性、动作及检索质量未确认；旧意见只随原report/request/payload/shot/actor，不自动成为新版结论。基础视觉v4与精分析v4为不同合同。

## 恢复位置

root顺序拥有retrieval、action_aliases行为测试、只读证据和公共文档；旧worker／worktree均冻结，无并行writer。

- 当前docs/exec-plans/sprint-retrieval-corpus-audit.md、report-2026-10-06-retrieval-corpus-audit.md和stage-progress；旧英文修复b7723aa／20c227c／1c7c278及对应query-audit报告保留历史。
- ignored artifacts/retrieval-corpus-audit/inventory.json、audit.json、after-fix.json、comparison.json、browser-report.json、production-report.json、双尺寸截图及脚本。comparison前后SHA a78cebdc68226c7f67fa106386e2be6c2613c56bd1ce4a05ddb7f38435cc42cf／ab4d8060d6fd6193229bb093c15c16d2e829144d4c42a7c2ba2a085d9a9f58b7。
- .cache/retrieval-corpus-verify.log、tests.xml、targeted.xml（首错误）、targeted-final.xml、package-receipt.json和previous/current-processes.json。包、JUnit和源码相符；ignore证据不可当远端已保存。
- 固定十位诊断b2c2a13已交付：原排名／缺位／已知重复、回看／下载不额外检索；上下文变化失效，人评字段为空。旧人工记录c759450及artifacts/detail-pilot-review-20261006/review-editor.html可用，归档新目录五文件；新精分析v4缺结果禁填，只有空记录往返，无新增人评。
- 双击Start-Workspace.cmd继续使用；启动／读取／搜索／刷新不新增付费分析。工具只在.tools/.venv/.cache，先env.ps1，Python -B；密钥／视频／生成媒体／数据库不入Git，保留未知成本。
