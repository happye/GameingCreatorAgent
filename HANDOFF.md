# 当前交接

更新时间：2026-10-05（Asia/Hong_Kong）。Codex、Claude Code、Grok Build 共用；历史见 progress.md，验收见 feature_list.json。

## 当前结论

root分支codex/visual-details；Demo412729d/CLI修正6730edc，主体合同2e95485→bb05b66、独立测试410bb245→cd1810c均已集成；最后完整verify967passed/1权限skip。用户提醒五小时额度剩9%，本轮已完成交接收尾，workers全部冻结，不启动新模型实验。F006/F009/F010保持false；工程检查、JSON和命中数不替代独立人评。

新 Completed run **f601fb9b3e734d5ea188fc15c790acbb**：artifacts/demo-phase0，54.743220s / 16 窗口 / 33 事件 / 0 转录；16 个视觉窗口首次尝试全部完成。prompt phase0-vision-v6 / hash a60d114d9dd8bf82c5d2ea62c30c4cfe2b4316b08de34ade3cba883d6de9ea00；pipeline phase0-analyze-detailed-v2。配置 config.detailed-v6.example.json。正文及 uncertainty 未发现独立 fN；18 个事件含待核对。模型估价 ¥0.10270124，unknown 0，providerElapsedMs 42467；不是账单。

## 已实现与验证

- V5/V6：1280 宽 / 9 图 / 3MiB / detail=original；V1–V4 保持 512 / 1MiB，旧 hash/parser 不变。衣着、外观、持有物、环境、效果写成紧凑事实；V6 先判断连续动作资格，要求不同源时刻和正确边界。
- 新事实的编号只允许当前事件已引用的原窗口帧，映射真实源时间；未引用或越界编号拒绝。旧事实不重写，用 legacy-frame-alias-neutral-v1 清理显示、视觉索引和下载；保留键盘 F1 与普通标识。
- UI 显示待核对、Completed detailed 优先；原始事实与旧篮子身份校验保留。检索 bm25-e5-rrf-v5，新 passage 文本 hash 隔离旧向量缓存，阈值及明确动作否定保护不改。CLI 普通/benchmark 保存 uncertainty/displayUncertainty，run-demo 显示待核对。
- **最新完整verify：967 passed / 1 Windows文件symlink权限skip，71.87s**；Ruff90文件、mypy51源文件、CLI与两次离线wheel通过。wheel SHA 79504099f604bc33810b4bc880ec2f05bf9096fd0b70347019163b02cf80e57d；日志.cache/detail-actor-final-verify.log。先前V6基线876项是历史，不是未验证当前代码。

## 实验、费用和限制

本轮已知估价 **¥0.23083920**，上限¥5；V5对照¥0.03676864、失败V5 ¥0.07282904、V6对照¥0.01854028、Atom V6完整run ¥0.10270124均unknown0。追加漫画PV后有**2次网络失败/用量未确认**，保留未知预留¥4.065536；本轮总承诺¥4.29637520，余¥0.70362480，不足单次保守预留¥2.032768，停止新API请求。未知预留不是实际账单，不得擅自当零或换项目清账。全部证据保持ignored。

追加漫画V6新项目artifacts/demo-visual-manga / run**0ba106578bc7435c8689d12892a35dfb**，95.175874s，原预算¥4.76916080。media/asr完成，第一vision窗口2次provider.network失败无usage，第三次被budget.exhausted本地阻止，0事件。日志.cache/detail-v6-manga-analyze.log及原SQLite账本保留。**不得再次创建run或retry清除未知承诺**；先厘清网络与费用/获得明确新预算。现有demo-phase0漫画V2、AtomV4/V6及默认Atom继续可用。后续纯合同/ports/sidecar开发不需要新API。

V5对照 artifacts/visual-details-atom-execute：28–32和35–39s，A=V4/512、B=V5/512同九帧，C=V5/1280同源时刻；8HTTP/72图。V6对照 artifacts/visual-details-v6-atom-execute：31.5–35.5s，A=V4/512、B=V6/512、C=V6/1280；4HTTP/36图。两组静图控制空、倒序发送前拒绝；V6跳过31.5s单帧首尾，轻微待机仍可能被算事件。

V5 run c78f204907e04eb3a2ac97a9017dcad9 保留 failed / 9 of 16窗口 / 24事件：uncertainty错误及两次相同端点错误，已停止重发，未放松parser。新V6仍有配饰/持有物分类和跨切镜连续性错误，例如28s将蓝色物体写为武器、38–39s声称切镜前后同一角色；不得据此确认具体武器、角色或技能名称。

**工作台自由长句尚无完整同主体保证（TD009）**：BM25/RRF可能把不同人物的白发、红衣组合命中；不索引uncertainty也不能抵消facts误认类别。纯typed AND已实现，下一步接独立精分析、sidecar与显式匹配结果；不以事件关键词AND冒充解决。

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

1. 核对status/HEAD/owner；新run与完整verify已落盘，不重复付费分析。
2. 最新全检已完成967pass/1权限skip，日志.cache/detail-actor-final-verify.log。接手仍先运行init -CheckOnly并核对工作树；未改源码不重复全套。查询/浏览器/启动已完成，不重复分析。
3. 下一开发任务：按sprint-actor-detail-matching任务2，在独立worktree新增application/detail_refinement.py，先冻结request/result、Provider/Store ports及canonical requestHash/event fingerprint。从Completed timeline验证raw candidate、原区间/证据/hash/源时钟和五项版本，兼容旧篮子；复用已集成typed合同，不重发旧run。
4. ports集成后再并行Provider/跨key预算与sidecar；UI附加full/partial/unverified及证据由root串行接。缺精分析结果应unverified，不拿自由文本做actor结构，不悄悄扩词表或自动推理。执行两真实候选试验前先处理网络与未知预算，默认开页/查询/刷新仍0API。
5. 同步HANDOFF/分工/feature_list/自身sprint，每验证节点提交。GitHub恢复后常规git push -u origin codex/visual-details；远端main仍仅最后已知72d692b，未确认最新状态，禁止强推。

GitHub github.com:443多次连接失败，远端最新状态未确认；本地提交不等于远端同步。完成后重试命令级HTTP/1.1常规push，禁止强推或改全局网络配置。

环境只用.tools/.venv/.cache，先env.ps1+Python -B；密钥只使用既有进程DEEPSEEK_API_KEY，不打印或复制聊天密钥。每个验证节点及长任务前更新sprint/HANDOFF并提交检查点，不能等额度提醒。详细失败记录见docs/exec-plans/sprint-visual-details.md。
