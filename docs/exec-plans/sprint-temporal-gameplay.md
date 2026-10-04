# F006 玩法时序理解修正

日期：2026-10-04；owner：Codex root，分支codex/temporal-gameplay。用户否决截图式描述的打Boss、跳跃、射击检索；这是定性失败，不虚构为独立固定十槽U10。F006/F009仍false。

## 问题与工程修正

旧v2一次请求已有5帧，但允许单帧事实/单帧事件，不能证明动作理解。保持旧prompt/config/run不可变，不靠降低检索阈值补理解缺失。

v3先要求主体→动作变化→可见结果、不同时间/不同图像证据、未知动作保守处理。Grok已集成并记录有限真实试验，root保留其全量未提交改动为4c37a63；只读复核确认报告与费用一致。旧v3漫画0–4s的B因evidence_outside_range被拒绝，原响应未保存，具体坏端点未知，不编造根因。

独立v4合同（d026103→42604f9，root联动b2daf1b）：模型用startFrameId/endFrameId与f0..f8引用，程序生成[firstUs,lastUs+1)；端点必须出现在有序证据内，至少两个不同时间和图像hash，最多3事件，静帧/单帧/乱序/未知/倒序边界拒绝。错误只有有限schemaError与整数/别名schemaDetail，不保存原响应。v1/v2/v3原prompt/hash保留，v4绑定temporal-actions-v1。

config.temporal.example.json显式使用v4（hash9ea350e10eb028f1f5e2dc7d355ebd1d080ad8ae8397eb709705a25773323f48），500ms/9帧/重叠2，仍约4秒跨度。config/SQLite白名单、独立pipeline、逐窗口checkpoint和恢复已接入，不改DB schema。默认config.example.json仍v2，run-demo通过-Config选择新版本。不能跨切镜或跨窗口无条件拼故事。

## 真实对照与费用

所有报告qualityGate=null、unknown0、非账单；输出目录均在ignored artifacts/，源视频留本地。仅选定图片送API，预发送账本保守预留1M输入/4096输出；默认试验预算¥5、请求上限不提升。

| 目录/案例 | 结果 | 已知API估价 |
| --- | --- | --- |
| temporal-gameplay-dry-1/2 | 旧v3两次冻结，无HTTP | 不计费 |
| temporal-gameplay-execute-1（Grok） | v2/A5事件，v3/B范围拒绝，static空，倒序本地拒绝；3次HTTP/23图 | ¥0.0075876 |
| temporal-v4-execute-0 | 0–4s A/v2稀5、B/v4密9、C/v4同5帧分别5/2/2事件，static空、倒序本地拒绝 | ¥0.0093252 |
| temporal-v4-execute-28 | 漫画28–32s A/B/C通过，B描述持续伤害/轻微位移；static幻觉被event_static_evidence拒绝 | ¥0.00974288 |
| temporal-v4-atom-8 | Atom8–12s B3个过程，jump与主动跳跃不确定性矛盾；C端点证据失败，static幻觉被拒绝 | ¥0.01037184 |

三个v4对照各4次HTTP/28图；合计¥0.02943992。A/B同时改变合同和密度，C控制同帧减少混淆。校验器拒绝假动作不是模型静帧控制通过；0–4s主要转场也不能证明玩法准确。

## 工作台可用新run

Atom实机PV54.743220s，SHA172e1139b477352db5e5fe2f3be3afb5171935c2edd8a2d0278a434212fd00fd。新run96b5f01530ce43e2944828fb0520b9b4在artifacts/demo-phase0完整Completed：16窗口/40事件/0转录，估价¥0.05029788。本轮3个v4对照加完整run¥0.0797378，不包含旧Grok试验。旧漫画111事件run f76f...不重写。

UI增加analysisKind身份，初次优先Completed temporal并标“连续动作（试验）”，旧run标“画面观察”。Start-Workspace.cmd（df475ef→0cc2c2f）默认隐藏启动本地Python -B并打开浏览器；health仓库/pid/parentPid判定就绪和复用，异仓库/旧端口不停止，15秒失败仅清理本次助手，日志/PID留.cache/workspace。正常启动不调用模型。运行方式/限制与共享指南已同步。

## 检查与未通过项

集成合同定向217 passed/1权限skip；否定修正前完整verify668 passed/1权限skip（65.98s）。最终5f15bab集成后完整verify **744 passed/1 Windows symlink权限skip（75.43s）**，Ruff80/mypy48/CLI/两次匹配离线wheel通过，SHA9f7160995598854ce863d91c1290931ee26552ff048b3462f45d8048d2aca166。启动器5项真实CMD/PowerShell生命周期通过，root实际8765 ready。工具收据曾仅有28stdlib pyc漂移，已从固定SHA项目归档恢复，receipt/程序/DLL未变，完整init通过。

真实Chromium报告temporal-workspace-atom-v4通过新run默认/标签、rank1播放至12.500001暂停、图片证据、乱序选片后的篮子/存储/JSON/CSV源时间排序、两桌面同屏/深滚动保持、390px无横溢出、汽车维修hybrid0和无JS错。只是界面合同，不是玩法质量。

初始检索诊断temporal-retrieval-atom-v4：jump hybrid3，其中49–49.5s明确说无跳跃。retrieval_negation b1e33a5→5f15bab修正为bm25-e5-rrf-v4：在排名时排除仅明确否认查询动作的事件，肯定/不确定描述和普通查询保留，否定意图查询只绕过规则保持兼容；原事实/embedding文本/hash/阈值不变。不是通用语义理解，worker167项行为/持久化/CLI通过。

修正后temporal-retrieval-atom-v4-negation五查询/三模式：jump lexical/hybrid2（11.5–12.5s、0–2s），49s否定事件排除；Boss/射击/汽车维修hybrid0、移动10，pure semantic各10。temporal-workspace-atom-v4-negation真实Chromium复测通过，使用3条移动候选验证同样界面合同，导出版本v4。生产8765 health匹配本仓库状态后重启到PID36692，HTTP jump2且版本v4；不将原jump3浏览器报告冒称修正后质量证据。

## 接手与后续

全部worker与旧worktree已冻结，不覆盖root；root独占集成/共享记录。完整verify、实际五查询/三模式、浏览器和健康匹配服务重启已完成。后续新任务先分配独占范围；篮子fixture不要求跳跃固定返回3条。每个节点同步HANDOFF/progress/assignments与Git，不等额度提醒。

10月5日收尾补查：完整init再次通过固定工具/运行库/media收据；默认Start-Workspace.cmd（未带-NoBrowser）实际退出0、复用新版PID36692并调用默认浏览器，工作台已可直接重测。发布目标为正常fast-forward的main与任务分支，先fetch确认origin/main仍317b22d且为祖先，禁止强推或覆盖其他Agent提交。

明确否定修正是有限语言规则，不能代替模型动作质量；下一步验证切镜/跨窗口/下落与跳跃区别、长动作和更合适视觉模型，冻结独立10–20会话人评后执行F006。正式桌面、渲染/发布/商业阶段不能由此次开发对照提前验收。工具/包/缓存保持项目隔离，密钥只在现有进程环境，素材/账本/DB不进Git。
