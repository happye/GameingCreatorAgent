# 当前交接

更新时间：2026-10-05（Asia/Hong_Kong）。Codex、Claude Code、Grok Build 共用；历史见 progress.md，验收见 feature_list.json。

## 当前结论

2026-10-05 Codex 已顺序接续 Grok，并保存继承检查点 `16f727f`。只读 sidecar 已接到 `/api/inspect`，timeline/candidates新增版本化detailRefinement；UI证据页显示未验证或按镜头/主体/部件展开已保存结构，复用不表示复合条件full。旧短ID/无base prompt hash数据为unsupported/unverified，原事实/排名/篮子/导出保留。新17项测试与相关回归 **88 passed / 1 Windows文件symlink权限skip（18.18s）**，Ruff/mypy54通过。完整verify与真实V6 smoke待执行；恢复以 `docs/exec-plans/sprint-detail-inspection.md` 为准。无新API，未知预留/F006/F009/F010不变。

以下为接续基线与已有实验记录，最新验证以本轮段落和sprint为准。

root分支codex/visual-details，HEAD `8b71c38`。精分析 sidecar 与共享预算会话已在 root 落地，未调用 API，未改 vision prompt、raw events 或 SQL。侧车按冻结 requestHash 保存不可变 request、追加 attempts 和原子 result；缺记录为 unverified。同一预算账本里的未知预留在恢复和另一个 budget 目录下仍然占额度。未完成尝试的检查在预算锁内再次执行，重叠的两次 `send_refinement` 只有一次调用 provider。定向 `tests/test_detail_budget_sidecar.py` 连续两次都是 9 passed（0.34s）。`tests/test_detail_refinement.py` 复核 6 passed（0.32s），Completed run `f601fb9b3e734d5ea188fc15c790acbb` 的事件 `0b8be73b204cceb6f0e37c7d` 仍保持原区间、证据 id、图像 hash 和整数源微秒；非视觉候选仍 unverified。新鲜进程两次 reuse-or-refuse 都是 unverified、provider 调用 0，request hash `6e9ee8f0c25212e7bd7c401a6dcfa972544e4121494100a7083a2270604c480f`。最新完整 verify **982 passed / 1 Windows 文件 symlink 权限 skip，68.06s**；Ruff 95 文件、mypy 54 源文件、CLI 与两次离线 wheel 通过。wheel SHA `cf3574ff00d50ffc4df52f0652921ee6fa34160e48b0356aba47320a5fe79330`。F006/F009/F010 保持 false。没有 retry 漫画 run `0ba106578bc7435c8689d12892a35dfb`。打Boss、跳跃、射击和复合主体查询都没有修好。

新 Completed run **f601fb9b3e734d5ea188fc15c790acbb**：artifacts/demo-phase0，54.743220s / 16 窗口 / 33 事件 / 0 转录；16 个视觉窗口首次尝试全部完成。prompt phase0-vision-v6 / hash a60d114d9dd8bf82c5d2ea62c30c4cfe2b4316b08de34ade3cba883d6de9ea00；pipeline phase0-analyze-detailed-v2。配置 config.detailed-v6.example.json。正文及 uncertainty 未发现独立 fN；18 个事件含待核对。模型估价 ¥0.10270124，unknown 0，providerElapsedMs 42467；不是账单。

## 已实现与验证

- V5/V6：1280 宽 / 9 图 / 3MiB / detail=original；V1–V4 保持 512 / 1MiB，旧 hash/parser 不变。衣着、外观、持有物、环境、效果写成紧凑事实；V6 先判断连续动作资格，要求不同源时刻和正确边界。
- 新事实的编号只允许当前事件已引用的原窗口帧，映射真实源时间；未引用或越界编号拒绝。旧事实不重写，用 legacy-frame-alias-neutral-v1 清理显示、视觉索引和下载；保留键盘 F1 与普通标识。
- UI 显示待核对、Completed detailed 优先；原始事实与旧篮子身份校验保留。检索 bm25-e5-rrf-v5，新 passage 文本 hash 隔离旧向量缓存，阈值及明确动作否定保护不改。CLI 普通/benchmark 保存 uncertainty/displayUncertainty，run-demo 显示待核对。
- **最新完整verify：982 passed / 1 Windows文件symlink权限skip，68.06s**；Ruff 95 文件、mypy 54 源文件、CLI与两次离线wheel通过。wheel SHA `cf3574ff00d50ffc4df52f0652921ee6fa34160e48b0356aba47320a5fe79330`。先前 981/973/967 是历史，不是未验证当前代码。

## 实验、费用和限制

本轮已知估价 **¥0.23083920**，上限¥5；V5对照¥0.03676864、失败V5 ¥0.07282904、V6对照¥0.01854028、Atom V6完整run ¥0.10270124均unknown0。追加漫画PV后有**2次网络失败/用量未确认**，保留未知预留¥4.065536；本轮总承诺¥4.29637520，余¥0.70362480，不足单次保守预留¥2.032768，停止新API请求。未知预留不是实际账单，不得擅自当零或换项目清账。全部证据保持ignored。

追加漫画V6新项目artifacts/demo-visual-manga / run**0ba106578bc7435c8689d12892a35dfb**，95.175874s，原预算¥4.76916080。media/asr完成，第一vision窗口2次provider.network失败无usage，第三次被budget.exhausted本地阻止，0事件。日志.cache/detail-v6-manga-analyze.log及原SQLite账本保留。**不得再次创建run或retry清除未知承诺**；先厘清网络与费用/获得明确新预算。现有demo-phase0漫画V2、AtomV4/V6及默认Atom继续可用。后续纯合同/ports/sidecar开发不需要新API。

V5对照 artifacts/visual-details-atom-execute：28–32和35–39s，A=V4/512、B=V5/512同九帧，C=V5/1280同源时刻；8HTTP/72图。V6对照 artifacts/visual-details-v6-atom-execute：31.5–35.5s，A=V4/512、B=V6/512、C=V6/1280；4HTTP/36图。两组静图控制空、倒序发送前拒绝；V6跳过31.5s单帧首尾，轻微待机仍可能被算事件。

V5 run c78f204907e04eb3a2ac97a9017dcad9 保留 failed / 9 of 16窗口 / 24事件：uncertainty错误及两次相同端点错误，已停止重发，未放松parser。新V6仍有配饰/持有物分类和跨切镜连续性错误，例如28s将蓝色物体写为武器、38–39s声称切镜前后同一角色；不得据此确认具体武器、角色或技能名称。

**工作台自由长句尚无完整同主体保证（TD009）**：BM25/RRF可能把不同人物的白发、红衣组合命中；不索引uncertainty也不能抵消facts误认类别。纯typed AND和精分析 request/ports 已实现，自由长句仍无严格保证；不以事件关键词AND冒充解决。

纯typed合同和离线matcher已实现：domain/actor_details.py与application/actor_detail_matching.py，同actor/同part_group/共同支持帧AND；属性仅在引用时钟内有效，未知不是否定，跨镜头不合并，单帧/同图不能变动作。schema actor-details-v1，词表actor-detail-vocabulary-v1，query schema actor-detail-query-schema-v1，query actor-detail-query-v1，matcher actor-detail-matcher-v1。canonical_constraint_json/constraint_hash供后续ports复用，未知词条明确拒绝。独立73domain+18matcher+3architecture联合94passed（0.32s）；**该matcher尚未接自由文本、CLI/UI、Provider或sidecar，因此工作台长句检索仍无严格保证**。

## 工作台与恢复顺序

双击 Start-Workspace.cmd 打开 http://127.0.0.1:8765/；已实际验证脚本复用服务，启动不分析或付费。生产默认已确认是新V6 / 33事件 / detailed。真实浏览器验证播放15.5–17s结束暂停、证据加载、筛选、篮子恢复/源序排序、JSON/CSV、两桌面尺寸同屏和手机无横溢。

服务已核对health/保存状态/项目内Python后停止旧PID2548，重新启动为PID38364 / parent27896；.cache/workspace/port-8765.json一致。**下次操作前重新核对health和状态，仅停止匹配的自有进程**。旧Atom V4及漫画snapshot SHA前后相同，原数据保留。

证据在artifacts/visual-detail-v6-delivery：retrieval-matrix.json（10查询×3模式）；browser-verified/browser-report.json（修正启动等待后defaultRunId也正确）、production-report.json、screenshots及两旧timeline SHA。查询无API：jump hybrid2；心形墨镜/指挥棒/场景均有候选；汽车维修hybrid0而semantic10；用户恶魔领主复合例hybrid8，属于证据不足的局部召回，不能宣称该内容存在。旧首次browser报告default值是读取占位符，验证脚本已改等时间轴加载，无产品逻辑变化。

- root：config/store/analysis/CLI/UIprofile、真实调用、查询/浏览器、共享文档与集成。
- detail_v6_completion：dff948e→02cb7b2已集成并冻结；.worktrees/detail-v6勿回写root。
- detail_retrieval_audit：.worktrees/actor-detail-spec / codex/actor-detail-spec，两篇规格b1d91bc→a7789b4已集成冻结，无API。
- detail_v6_completion新合同：.worktrees/actor-detail-contract / codex/actor-detail-contract，2e95485→bb05b66已集成冻结，4文件，owner定向21项/类型/格式通过；不修改CLI/UI/provider/store。
- detail_retrieval_audit新测试：.worktrees/actor-detail-tests / codex/actor-detail-tests，410bb245已集成冻结；最终钉2e95485联合94passed/0skip，73新domain反例，own sprint已在root。旧spec worktree冻结，禁止共享writer。
- 其他V5 vision/presentation/pilot worktrees全部冻结。

本轮正在完成只读检查接入的完整verify与真实V6复测。下一开发任务：独立精分析Provider的冻结prompt/parser与完整attempt metadata、取消/中断恢复合同先做离线fixture；随后按typed QueryConstraint接纯matcher，继续显式版本读取。未知预留得到处理/明确新预算前不要发新API；不要宣称打Boss、跳跃、射击或复合主体查询已修好。

恢复时先核对 status/HEAD。本轮 ports 改动尚未提交，不要强推。未知预留 ¥4.065536 仍在，禁止 retry `0ba106578bc7435c8689d12892a35dfb` 或换目录清账。默认开页、查询和刷新仍是 0 API。远端 main 仍只记录到最后已知 `72d692b`，未再确认。

GitHub github.com:443多次连接失败，远端最新状态未确认；本地提交不等于远端同步。完成后重试命令级HTTP/1.1常规push，禁止强推或改全局网络配置。

环境只用.tools/.venv/.cache，先env.ps1+Python -B；密钥只使用既有进程DEEPSEEK_API_KEY，不打印或复制聊天密钥。每个验证节点及长任务前更新sprint/HANDOFF并提交检查点，不能等额度提醒。详细失败记录见docs/exec-plans/sprint-visual-details.md。
