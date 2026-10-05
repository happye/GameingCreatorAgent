# 当前交接

更新时间：2026-10-06（Asia/Hong_Kong）。Codex、Claude Code、Grok Build 共用；历史见 progress.md，验收见 feature_list.json。

## 当前结论

当前root codex/visual-details，实现23d8422（独立精分析/恢复）与a6eb196（typed query CLI/profile）。完整verify **1062 passed / 1 Windows文件symlink权限skip（93.59s）**，Ruff103/mypy58/CLI与重复离线wheel通过，日志.cache/detail-query-verify.log。定向Provider167、query82通过。后续仅文档/本地证据更新，无源码再改。

用户追加最高¥4.04，并明确允许共6张注册源帧/帧ID/提示词参数发送至DeepSeek chat/completions；仅两候选各1次、总2次、无retry，均Completed。合计估价 **¥0.01850612，新增unknown0**；旧未知¥4.065536保留，全任务已知¥0.24934532/总承诺¥4.31488132。两个复合条件均partial，不宣称内容已通过。真实v2结果已发布，旧base事件/证据/调用账本不变；humanLabels/qualityGate=null，F006/F009/F010=false。

人工核对入口 **artifacts/detail-query-validation/human-review.html**（6帧，桌面/手机无横溢、0页面错误）；完整结果pilot-report.json、请求proposal、real-read-report.json。35–36s三个主体未跨actor拼接；但模型把同衣物形状/颜色分成不同partId，后续需独立新版本纠正，不修改已冻结v2结果。28–29s模型记录蓝发/蓝色扁平物并拆成三个shot，白发条件未满足；武器类别仍无支持，待用户核对。

match-details已接严格query-v1清单与独立match记录，CLI默认v2，检查API detailProfile默认v1；页面仍v1/自由查询无严格AND。新版生产服务PID36320/parent24836仅快照，已验证v2 API/33事件，重启前须重验身份。前两次push因GitHub443超时，第三次正常push成功上传30c44ae；独立ls-remote与本地HEAD一致，未更新main或强推。后续仅同步状态文档，最新HEAD以git核对为准。

2026-10-05 Codex已顺序接续Grok，继承检查点16f727f、实现96f6c82；最新HEAD见git log。只读sidecar已接到/api/inspect，UI证据页显示未验证或按镜头/主体/部件展开已保存结构。复用不表示复合条件full；旧短ID/无base prompt hash数据为unsupported/unverified，原事实/排名/篮子/导出保留。最新完整verify：999 passed / 1 Windows文件symlink权限skip（142.12s），Ruff96文件、mypy54、CLI和两次离线wheel通过，SHA 431d9f32f5c774ffecb351d2d55f50a4a7a1fbdd72bc9787cb7c40c4efc05b0e。新17项及相关定向回归88 passed/1skip。真实V6浏览器smoke和生产读取通过，默认33事件；V2/V4/V6快照及sidecar文件未变。证据artifacts/detail-inspection-validation和.cache/detail-inspection-verify.log；无新付费API，未知预留与F006/F009/F010不变。

以下为接续基线与已有实验记录，最新验证以本轮段落和sprint为准。

接续基线8b71c38及Grok未提交的request/sidecar/共享预算已保存16f727f。未知预留在恢复/跨budget目录仍占额度，锁内复查阻止重叠发送。原982项验证是历史。V6目标事件0b8be73b204cceb6f0e37c7d实际requestHash为229a8bcb9bee1f017854108751d89840f458040fd14cdd3490e5c2fd56d00279；16f727f模块与当前模块canonical request逐字段相同，旧文档6e9ee8...无法复现，已更正。真实数据尚无已保存主体结构，页面显示未验证；reused展示由合成侧车验证，不冒充真实精分析。没有retry漫画失败run或玩法/复合检索人评通过。

新 Completed run **f601fb9b3e734d5ea188fc15c790acbb**：artifacts/demo-phase0，54.743220s / 16 窗口 / 33 事件 / 0 转录；16 个视觉窗口首次尝试全部完成。prompt phase0-vision-v6 / hash a60d114d9dd8bf82c5d2ea62c30c4cfe2b4316b08de34ade3cba883d6de9ea00；pipeline phase0-analyze-detailed-v2。配置 config.detailed-v6.example.json。正文及 uncertainty 未发现独立 fN；18 个事件含待核对。模型估价 ¥0.10270124，unknown 0，providerElapsedMs 42467；不是账单。

## 已实现与验证

- V5/V6：1280 宽 / 9 图 / 3MiB / detail=original；V1–V4 保持 512 / 1MiB，旧 hash/parser 不变。衣着、外观、持有物、环境、效果写成紧凑事实；V6 先判断连续动作资格，要求不同源时刻和正确边界。
- 新事实的编号只允许当前事件已引用的原窗口帧，映射真实源时间；未引用或越界编号拒绝。旧事实不重写，用 legacy-frame-alias-neutral-v1 清理显示、视觉索引和下载；保留键盘 F1 与普通标识。
- UI 显示待核对、Completed detailed 优先；原始事实与旧篮子身份校验保留。检索 bm25-e5-rrf-v5，新 passage 文本 hash 隔离旧向量缓存，阈值及明确动作否定保护不改。CLI 普通/benchmark 保存 uncertainty/displayUncertainty，run-demo 显示待核对。
- 检查视图基线999 passed/1权限skip及142.12s为历史；最新完整1062/1skip见当前结论。当前两个wheel同SHA `f4282ed7b02c315a3d2cb6c8acd16d8cd4bddd2ada9c655cda9970123a1be799`；未改基础vision/检索/导出源码。

## 实验、费用和限制

2026-10-05原预算基线：已知¥0.23083920、原上限¥5；V5对照¥0.03676864、失败V5 ¥0.07282904、V6对照¥0.01854028、Atom V6完整run ¥0.10270124。漫画两网络失败未知预留¥4.065536、原承诺¥4.29637520，保留不改。2026-10-06另获两候选/¥4.04/指定DeepSeek传输授权，已完成2次/¥0.01850612，费用汇总见当前结论；不能因预算余额再请求。未知预留不是账单，不得当零或换目录清账，媒体/数据库/证据保持ignored。

追加漫画V6新项目artifacts/demo-visual-manga / run**0ba106578bc7435c8689d12892a35dfb**，95.175874s，原预算¥4.76916080。media/asr完成，第一vision窗口2次provider.network失败无usage，第三次被budget.exhausted本地阻止，0事件。日志.cache/detail-v6-manga-analyze.log及原SQLite账本保留。**不得再次创建run或retry清除未知承诺**；先厘清网络与费用/获得明确新预算。现有demo-phase0漫画V2、AtomV4/V6及默认Atom继续可用。后续纯合同/ports/sidecar开发不需要新API。

V5对照 artifacts/visual-details-atom-execute：28–32和35–39s，A=V4/512、B=V5/512同九帧，C=V5/1280同源时刻；8HTTP/72图。V6对照 artifacts/visual-details-v6-atom-execute：31.5–35.5s，A=V4/512、B=V6/512、C=V6/1280；4HTTP/36图。两组静图控制空、倒序发送前拒绝；V6跳过31.5s单帧首尾，轻微待机仍可能被算事件。

V5 run c78f204907e04eb3a2ac97a9017dcad9 保留 failed / 9 of 16窗口 / 24事件：uncertainty错误及两次相同端点错误，已停止重发，未放松parser。新V6仍有配饰/持有物分类和跨切镜连续性错误，例如28s将蓝色物体写为武器、38–39s声称切镜前后同一角色；不得据此确认具体武器、角色或技能名称。

**工作台自由长句尚无完整同主体保证（TD009）**：BM25/RRF可能把不同人物的白发、红衣组合命中；不索引uncertainty也不能抵消facts误认类别。纯typed AND和精分析 request/ports 已实现，自由长句仍无严格保证；不以事件关键词AND冒充解决。

typed合同/纯matcher、独立Provider、持久侧车和match-details CLI已接通：同actor/同part_group/共同支持帧AND；未知不是否定、跨镜头不合并、单帧/同图不能变动作。schema actor-details-v1，词表actor-detail-vocabulary-v1，query-schema-v1/query-v1/matcher-v1保持冻结。纯合同独立94项为历史证据；最新工程结果见上方。**页面自由长句尚未解析typed约束，因此仍无严格同主体保证。**

## 工作台与恢复顺序

双击 Start-Workspace.cmd 打开 http://127.0.0.1:8765/；已实际验证脚本复用服务，启动不分析或付费。生产默认已确认是新V6 / 33事件 / detailed。真实浏览器验证播放15.5–17s结束暂停、证据加载、筛选、篮子恢复/源序排序、JSON/CSV、两桌面尺寸同屏和手机无横溢。

生产服务已重新核对health、保存状态、父PID、项目Python路径与命令；仅停止匹配旧PID42408，启动新版PID49020/parent35808，.cache/workspace/port-8765.json一致，启动器已复用。真实浏览器默认V6/33事件并显示主体详情未验证。下次重新核对health和状态，仅停止匹配的自有进程。V2/V4/V6快照SHA及sidecar文件前后一致。

证据在artifacts/visual-detail-v6-delivery：retrieval-matrix.json（10查询×3模式）；browser-verified/browser-report.json（修正启动等待后defaultRunId也正确）、production-report.json、screenshots及两旧timeline SHA。查询无API：jump hybrid2；心形墨镜/指挥棒/场景均有候选；汽车维修hybrid0而semantic10；用户恶魔领主复合例hybrid8，属于证据不足的局部召回，不能宣称该内容存在。旧首次browser报告default值是读取占位符，验证脚本已改等时间轴加载，无产品逻辑变化。

- root：config/store/analysis/CLI/UIprofile、真实调用、查询/浏览器、共享文档与集成。
- detail_v6_completion：dff948e→02cb7b2已集成并冻结；.worktrees/detail-v6勿回写root。
- detail_retrieval_audit：.worktrees/actor-detail-spec / codex/actor-detail-spec，两篇规格b1d91bc→a7789b4已集成冻结，无API。
- detail_v6_completion新合同：.worktrees/actor-detail-contract / codex/actor-detail-contract，2e95485→bb05b66已集成冻结，4文件，owner定向21项/类型/格式通过；不修改CLI/UI/provider/store。
- detail_retrieval_audit新测试：.worktrees/actor-detail-tests / codex/actor-detail-tests，410bb245已集成冻结；最终钉2e95485联合94passed/0skip，73新domain反例，own sprint已在root。旧spec worktree冻结，禁止共享writer。
- 其他V5 vision/presentation/pilot worktrees全部冻结。

下一任务：接收两样本独立人工反馈；离线改进同一衣物/持有物part绑定合同，用新版本保留v2冻结身份；再接页面typed条件与只读成本历史。两次授权调用额度已按“次数”用完，不能因剩余预算再发第三次或retry；新实验须另明确候选/目的地/预算。不要宣称Boss、跳跃、射击或复合主体质量已通过。

恢复时先核对status/HEAD。继承ports/sidecar已保存16f727f，检查视图实现96f6c82；不要强推。未知预留¥4.065536仍在，禁止retry漫画0ba106578bc7435c8689d12892a35dfb或换目录清账。默认开页、查询和刷新仍是0付费API；本轮远端同步结果见sprint-detail-inspection，不改main或合并未验收特性。

用户随后明确授权仅推送codex/visual-details到https://github.com/happye/GameingCreatorAgent。普通HTTP/1.1 push已成功，新建远端工作分支并上传00f2796；未更新main或强推。紧随的独立ls-remote因GitHub443间歇连接失败未确认，后续同步记录提交后再次核对；最终状态以Git和sprint-detail-inspection为准。先前自动审批拒绝已通过用户明确授权解决，没有绕过审核或改全局网络配置。

环境只用.tools/.venv/.cache，先env.ps1+Python -B；密钥只使用既有进程DEEPSEEK_API_KEY，不打印或复制聊天密钥。每个验证节点及长任务前更新sprint/HANDOFF并提交检查点，不能等额度提醒。详细失败记录见docs/exec-plans/sprint-visual-details.md。
