# 当前交接

更新时间：2026-10-05（Asia/Hong_Kong，10月4日实验的收尾）。Codex、Claude Code、Grok Build共用此入口；历史见progress.md，验收见feature_list.json。

## 当前状态

**最新真实对照**：visual-details-atom-execute完成，2窗口A/B/C均3事件、static均空、倒序均发送前拒绝；8HTTP/72图、估价¥0.03676864、unknown0，非账单。V5细节增加且无正文alias，仍有护目镜/发饰混淆、衣着色不准与跨切镜连贯误判，不能当质量通过。root开始完整新Atom V5run（预算¥4.96323136，合计本轮上限5元），新runId须由CLI落盘后更新；不要重跑旧run。完整verify含pilot正在.cache/detail-verify-final.log执行。8765还是旧代码，待新run及浏览器验证后匹配PID重启。

**真实实验准备已保存**：detail_pilot944fb42→32fe12c已集成并冻结，9项root复测通过。无API dry `artifacts/visual-details-atom-dry`已冻结28–32和35–39s同源时刻对照；root即将执行新`artifacts/visual-details-atom-execute`（8HTTP/预算¥5，每case90s，含静帧/倒序，默认humanLabels/qualityGate=null）。paid开始前还无新费用；进度与逐case报告原子保存。完整新run待对照结果再做，总本轮实际/未知承诺上限¥5。恢复先查这两个report/invocations，勿重放已发请求。此前838verify是在新pilot集成前；新pilot9项另列。

**最新检查点**：完整verify838passed/1权限skip（81.70s），Ruff83/mypy49/CLI/离线重复wheel通过，SHA74728027088611445833fc4cb8802dbcaec8ca1a255b8357e0f91917c6bc459e；此前252/171为定向验证。只读审查发现正文别名可能越出当前事件证据，root已限制为事件已引用的原窗口别名，新增6回归，98项通过。对照脚本仍worker验证中；未新API调用，8765未重启。GitHub包括进程内HTTP/1.1重试仍443超时，DeepSeek API已只读确认可达。

**本轮集成快照（2026-10-05，覆盖下文旧744基线）**：rootcodex/visual-details，vision56b02e2→903c9cc、presentationa160116→86c229c已集成。V5prompt/hash、config.detailed.example.json、详细pipeline/1280宽/旧512隔离已实现；UI优先Completed V5并显示不确定性，旧事实/篮子raw校验不变，检索bm25-e5-rrf-v5。Provider/config/resume252项与显示/检索171项通过（另1权限skip）；完整verify/新真实API实验/新run未执行。detail_pilot.worktrees/detail-pilot独占新对照脚本和测试，root负责付费执行；其他新worker已冻结。首次浏览器ERR_UNSAFE_PORT由共享fixture高端口修复；171复测通过。GitHub443连接失败，工作分支远程同步待重试，本地进度已提交。当前8765仍旧进程，不代表新代码已上线；不能宣布细节效果或F006/F009/F010通过。

**新任务进行中（2026-10-05）**：用户要求可检索的衣着/装备/外观/背景/招式细节，以及修正文中的f0/f1。root已从72d692b切codex/visual-details，计划见sprint-visual-details。detail_vision/detail_presentation在各自独立worktree拥有provider与显示/索引独占文件；不可覆盖root。新V5/1280宽/可见细节绑定与旧文本投影正在开发，尚无新API调用、尚无新效果。以下72d692b与744项检查是上一轮基线，不替代本轮验证。

用户要求复核Grok、按F006连续玩法反馈修正并提供一键启动。本轮已保存Grok改动4c37a63、v4帧边界42604f9/b2daf1b、启动器0cc2c2f与否定召回5f15bab。root分支codex/temporal-gameplay；收尾文档提交见git log，已验证代码可正常fast-forward同步main，远端状态以git核对，不能把本地commit当已推送。之前GitHub443一次失败后，f3e98e8检查点重试推送成功。

**F006仍未通过，F009仍false。** 新模型开始描述动作变化，但存在跨镜头关联、标签与不确定性矛盾、静帧幻觉；校验器拒绝非法事件不代表模型理解正确。独立人工固定十槽U10没有完成，不能由Agent代替。

## 用户现在可以测试

双击根目录Start-Workspace.cmd：隐藏启动项目内Python服务并自动打开浏览器；重复启动复用同仓库服务。启动不分析视频、不调用付费API。命令行可用 ./scripts/start-workspace.ps1 -NoBrowser 或 -Port 8766。日志/PID在.cache/workspace；端口被其他/旧服务占用时清楚报错，绝不停止它。

已核对旧health与本次PID记录后重启本仓库工作台：http://127.0.0.1:8765/，当前health PID36692（后续可能改变，必须重新核对）。默认项目demo-phase0、Completed连续动作试验run **96b5f01530ce43e2944828fb0520b9b4**。实际8765 HTTP查询确认retrievalVersion为bm25-e5-rrf-v4。

新素材：Atom实机PV，54.743220s，SHA172e1139b477352db5e5fe2f3be3afb5171935c2edd8a2d0278a434212fd00fd；v4/2FPS/9帧/重叠2，16窗口、40事件、0转录，完整Completed。API估价¥0.05029788，unknown0，非账单。旧漫画run f76f5d6495314c04ae04083614d4afd6 的111条画面观察原样保留。

修正后的检索（artifacts/temporal-retrieval-atom-v4-negation/report.json）：hybrid跳跃2，分别11.5–12.5s和0–2s，待独立人工判断；明确否定跳跃的49–49.5s已被排除。Boss/射击/汽车维修0，移动10。Pure semantic每条仍返回10，未校准。修正前3条基线原样留在temporal-retrieval-atom-v4/report.json；不能把候选数当有用事件数。

## 验证与费用证据

- 最新完整verify：744 passed/1 Windows文件symlink权限skip，75.43s；Ruff80文件、mypy48、CLI与两次离线wheel通过，SHA 9f7160995598854ce863d91c1290931ee26552ff048b3462f45d8048d2aca166。旧668项报告是修正前基线。
- 启动器5项真实PowerShell/CMD生命周期通过：任意cwd、复用/并发单PID、foreign端口保护、带空格路径/快速退出7、15秒超时清理本次venv父/子。不使用WMI/taskkill、安装包或全局配置。Worker证据sprint-workspace-launcher-worker.md；root实际8765启动通过。
- root也执行了默认Start-Workspace.cmd，退出0、复用PID36692并调用系统默认浏览器打开工作台；不是仅交付-NoBrowser测试版本。
- Chromium真实新Atom跳跃查询检查通过，artifacts/temporal-workspace-atom-v4：默认新run/“连续动作（试验）”、40事件/3候选，rank1播放到12.500001暂停、图证据、乱序选择后篮子/存储/JSON/CSV源时间排序、两桌面同屏/深滚动保持、390px无横溢出、汽车维修0、无JS错。此报告包含否定误召回，证明界面合同，不证明玩法质量。
- 修正后Chromium复测temporal-workspace-atom-v4-negation通过，使用3条移动候选验证同样播放/证据/布局/排序/导出/恢复合同，记录新retrievalVersion；没有为满足篮子fixture硬凑跳跃数。生产8765另实测jump2且不含49s否定事件。浏览器成功仍不是质量验收。
- 有界真实实验：temporal-v4-execute-0 completed，A/B/C=5/2/2事件，static空、倒序本地拒绝；4次调用估价¥0.0093252。temporal-v4-execute-28 completed_with_failures，A/B/C通过、static幻觉被event_static_evidence拒绝；4次¥0.00974288。temporal-v4-atom-8 completed_with_failures，B3事件（jump/下落歧义），C边界证据失败、static被拒绝；4次¥0.01037184。均qualityGate=null/unknown0/非账单。三次pilot加完整run本轮已知API估价¥0.0797378；旧Grok v3试验¥0.0075876另列，不重复计入。
- 工具receipt曾发现28个stdlib pyc漂移；仅从项目内固定SHA归档恢复这些文件，receipt/程序/DLL未改，完整init通过。始终env.ps1 + Python -B，禁止全局安装。

## 当前归属与下一步

root独占公共文档、UI/API、pilot、配置/存储/analysis和集成。temporal_frame_contract d026103已集成42604f9、workspace_launcher df475ef已集成0cc2c2f，worktree冻结；旧vision/pilot/workspace worktree也冻结，不覆盖root。两次只读复核未发现新增合同/兼容/安全缺陷，不是质量认可。

retrieval_negation b1e33a5已集成5f15bab并冻结。v4检索在排名时排除仅明确否认查询动作的事件，保留另有肯定/不确定描述与普通查询；否定意图查询绕过该规则，只保持兼容，未实现通用否定理解。原事实、embedding文本/hash、阈值和旧搜索记录不变，167项worker联合行为/持久化/CLI检查通过，root真实五查询/三模式及完整verify复测通过。

接续：等待用户使用新run回看玩法与时间范围；继续TD004/TD007的模型动作/跨镜头/长窗口验证和独立人评。先冻结开发动作对照，再比较更合适Provider/候选精分析；不用重跑旧完整视频碰运气，不调低阈值冒充改善。正式F006需独立录制会话/人工标签；仍不能先转正式桌面/渲染/商业阶段。全部worker冻结，下一任务须重新分配独占范围。

恢复先读AGENTS、feature_list、shared workflow，检查git status/分支/文件归属、run状态、报告。素材/DB/模型在ignored目录，不随clone；配置更改创建新run，原run resume保留原prompt/预算/窗口。新分析显式config.temporal.example.json；默认config.example.json仍v2。密钥只使用现有进程DEEPSEEK_API_KEY，不打印/复制聊天密钥。每个实现/验证节点主动保存进度和Git检查点，不等额度提醒。
