# 当前交接

更新时间：2026-10-05（Asia/Hong_Kong）。Codex、Claude Code、Grok Build 共用；历史见 progress.md，验收见 feature_list.json。

## 当前结论

root 分支 codex/visual-details，代码检查点 c400188、规格 a7789b4。额度中断后已核对并继续：V6完整分析、30组离线查询、真实浏览器和启动验收已完成，主体/部件AND合同在独立worktree开发。F006/F009/F010保持false；工程检查、JSON合法及命中数不替代独立人评。

新 Completed run **f601fb9b3e734d5ea188fc15c790acbb**：artifacts/demo-phase0，54.743220s / 16 窗口 / 33 事件 / 0 转录；16 个视觉窗口首次尝试全部完成。prompt phase0-vision-v6 / hash a60d114d9dd8bf82c5d2ea62c30c4cfe2b4316b08de34ade3cba883d6de9ea00；pipeline phase0-analyze-detailed-v2。配置 config.detailed-v6.example.json。正文及 uncertainty 未发现独立 fN；18 个事件含待核对。模型估价 ¥0.10270124，unknown 0，providerElapsedMs 42467；不是账单。

## 已实现与验证

- V5/V6：1280 宽 / 9 图 / 3MiB / detail=original；V1–V4 保持 512 / 1MiB，旧 hash/parser 不变。衣着、外观、持有物、环境、效果写成紧凑事实；V6 先判断连续动作资格，要求不同源时刻和正确边界。
- 新事实的编号只允许当前事件已引用的原窗口帧，映射真实源时间；未引用或越界编号拒绝。旧事实不重写，用 legacy-frame-alias-neutral-v1 清理显示、视觉索引和下载；保留键盘 F1 与普通标识。
- UI 显示待核对、Completed detailed 优先；原始事实与旧篮子身份校验保留。检索 bm25-e5-rrf-v5，新 passage 文本 hash 隔离旧向量缓存，阈值及明确动作否定保护不改。CLI 普通/benchmark 保存 uncertainty/displayUncertainty，run-demo 显示待核对。
- **完整 verify：876 passed / 1 Windows 文件 symlink 权限 skip，78.81s**；Ruff86文件、mypy49源文件、CLI与两次离线wheel通过。wheel SHA 5fc900a156bf27011c648f26b0c60ab4a944f6eaafc4396d24f6efd6614c7836；日志 .cache/detail-v6-verify.log。

## 实验、费用和限制

本轮细节任务全部成功、失败及控制请求合计估价 **¥0.23083920 / unknown 0**，上限 ¥5。组成：V5对照 ¥0.03676864、失败V5 run ¥0.07282904、V6对照 ¥0.01854028、新V6完整run ¥0.10270124。费用不含旧V4历史实验，不是账单；全部证据目录保持 ignored。

V5对照 artifacts/visual-details-atom-execute：28–32和35–39s，A=V4/512、B=V5/512同九帧，C=V5/1280同源时刻；8HTTP/72图。V6对照 artifacts/visual-details-v6-atom-execute：31.5–35.5s，A=V4/512、B=V6/512、C=V6/1280；4HTTP/36图。两组静图控制空、倒序发送前拒绝；V6跳过31.5s单帧首尾，轻微待机仍可能被算事件。

V5 run c78f204907e04eb3a2ac97a9017dcad9 保留 failed / 9 of 16窗口 / 24事件：uncertainty错误及两次相同端点错误，已停止重发，未放松parser。新V6仍有配饰/持有物分类和跨切镜连续性错误，例如28s将蓝色物体写为武器、38–39s声称切镜前后同一角色；不得据此确认具体武器、角色或技能名称。

**任意复合属性AND / 同一主体保证尚未实现（TD009）**：自由文本BM25/RRF可能把不同人物的白发、红衣组合命中；不索引uncertainty也不能抵消事实中误认的物品类别。下一步采用独立精分析记录、主体属性及证据绑定、严格匹配和显式部分匹配，不以事件关键词AND冒充解决。

## 工作台与恢复顺序

双击 Start-Workspace.cmd 打开 http://127.0.0.1:8765/；已实际验证脚本复用服务，启动不分析或付费。生产默认已确认是新V6 / 33事件 / detailed。真实浏览器验证播放15.5–17s结束暂停、证据加载、筛选、篮子恢复/源序排序、JSON/CSV、两桌面尺寸同屏和手机无横溢。

服务已核对health/保存状态/项目内Python后停止旧PID2548，重新启动为PID38364 / parent27896；.cache/workspace/port-8765.json一致。**下次操作前重新核对health和状态，仅停止匹配的自有进程**。旧Atom V4及漫画snapshot SHA前后相同，原数据保留。

证据在artifacts/visual-detail-v6-delivery：retrieval-matrix.json（10查询×3模式）；browser-verified/browser-report.json（修正启动等待后defaultRunId也正确）、production-report.json、screenshots及两旧timeline SHA。查询无API：jump hybrid2；心形墨镜/指挥棒/场景均有候选；汽车维修hybrid0而semantic10；用户恶魔领主复合例hybrid8，属于证据不足的局部召回，不能宣称该内容存在。旧首次browser报告default值是读取占位符，验证脚本已改等时间轴加载，无产品逻辑变化。

- root：config/store/analysis/CLI/UIprofile、真实调用、查询/浏览器、共享文档与集成。
- detail_v6_completion：dff948e→02cb7b2已集成并冻结；.worktrees/detail-v6勿回写root。
- detail_retrieval_audit：.worktrees/actor-detail-spec / codex/actor-detail-spec，两篇规格b1d91bc→a7789b4已集成冻结，无API。
- detail_v6_completion新任务：.worktrees/actor-detail-contract / codex/actor-detail-contract，独占新domain/actor_details.py、application/actor_detail_matching.py、test_actor_detail_matching.py及own sprint；纯合同/匹配器进行中，不修改CLI/UI/provider/store。
- detail_retrieval_audit新测试：.worktrees/actor-detail-tests / codex/actor-detail-tests，独占test_actor_details.py与own sprint；先读合同草稿，冻结后联合复测。旧spec worktree保持冻结，禁止共享writer。
- 其他V5 vision/presentation/pilot worktrees全部冻结。

1. 核对status/HEAD/owner；新run与完整verify已落盘，不重复付费分析。
2. 查询/浏览器/启动已完成，不重复付费分析。查当前actor-detail-contract状态，复核同人/同部件/共同支持帧与unknown规则，集成独占提交。
3. 合同定型后按sprint-actor-detail-matching做独立精分析ports，再拆Provider/预算与sidecar；普通搜索仍离线，完整复合匹配未接入工作台。
4. 新合同集成后跑相关与完整verify，同步规格/手册/feature_list/分工/progress，保存本地提交；GitHub恢复时常规补推。

GitHub github.com:443多次连接失败，远端最新状态未确认；本地提交不等于远端同步。完成后重试命令级HTTP/1.1常规push，禁止强推或改全局网络配置。

环境只用.tools/.venv/.cache，先env.ps1+Python -B；密钥只使用既有进程DEEPSEEK_API_KEY，不打印或复制聊天密钥。每个验证节点及长任务前更新sprint/HANDOFF并提交检查点，不能等额度提醒。详细失败记录见docs/exec-plans/sprint-visual-details.md。
