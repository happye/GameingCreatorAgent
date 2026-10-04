# 当前交接

更新时间：2026-10-04（Asia/Hong_Kong）。Codex、Claude Code、Grok Build 共用此入口；历史见 progress.md，验收见 feature_list.json。

## 当前状态

用户要求复核 Grok、按 F006 连续玩法反馈修正并提供一键启动。本轮已保存 Grok 改动为4c37a63、集成v4帧边界合同42604f9/b2daf1b及启动器0cc2c2f。分支codex/temporal-gameplay；main仍为上一轮317b22d。最新远端检查点需以git核对，不能把本地commit当已推送。

**F006仍未通过，F009仍false。** 新模型开始描述动作变化，但存在跨镜头关联、标签与不确定性矛盾、静帧幻觉；校验器拒绝非法事件不代表模型理解正确。独立人工固定十槽U10没有完成，不能由Agent代替。

## 用户现在可以测试

双击根目录Start-Workspace.cmd：隐藏启动项目内Python服务并自动打开浏览器；重复启动复用同仓库服务。启动不分析视频、不调用付费API。命令行可用 ./scripts/start-workspace.ps1 -NoBrowser 或 -Port 8766。日志/PID在.cache/workspace；端口被其他/旧服务占用时清楚报错，绝不停止它。

已启动本仓库工作台：http://127.0.0.1:8765/，health返回PID76732（helper103048，可能在后续已退出，必须重新核对）。默认项目demo-phase0、Completed连续动作试验run **96b5f01530ce43e2944828fb0520b9b4**。

新素材：Atom实机PV，54.743220s，SHA172e1139b477352db5e5fe2f3be3afb5171935c2edd8a2d0278a434212fd00fd；v4/2FPS/9帧/重叠2，16窗口、40事件、0转录，完整Completed。API估价¥0.05029788，unknown0，非账单。旧漫画run f76f5d6495314c04ae04083614d4afd6 的111条画面观察原样保留。

检索基线（artifacts/temporal-retrieval-atom-v4/report.json）：hybrid跳跃3，其中11.5–12.5s和0–2s为待人工判断候选，第三49–49.5s明说无跳跃，是确定的否定表述误召回；Boss/射击/汽车维修0，移动10。Pure semantic每条仍返回10，未校准。不要把候选数当有用事件数。

## 验证与费用证据

- 完整verify：668 passed/1 Windows文件symlink权限skip，65.98s；Ruff79文件、mypy48、CLI与两次离线wheel通过，SHA ee68d460f9d4f02ff454ca206e009c4d2f9f0dd4b93c96fc7287de891bbf11ab。这是否定表述修正前基线，后续集成须重检。
- 启动器5项真实PowerShell/CMD生命周期通过：任意cwd、复用/并发单PID、foreign端口保护、带空格路径/快速退出7、15秒超时清理本次venv父/子。不使用WMI/taskkill、安装包或全局配置。Worker证据sprint-workspace-launcher-worker.md；root实际8765启动通过。
- Chromium真实新Atom跳跃查询检查通过，artifacts/temporal-workspace-atom-v4：默认新run/“连续动作（试验）”、40事件/3候选，rank1播放到12.500001暂停、图证据、乱序选择后篮子/存储/JSON/CSV源时间排序、两桌面同屏/深滚动保持、390px无横溢出、汽车维修0、无JS错。此报告包含否定误召回，证明界面合同，不证明玩法质量。
- 有界真实实验：temporal-v4-execute-0 completed，A/B/C=5/2/2事件，static空、倒序本地拒绝；4次调用估价¥0.0093252。temporal-v4-execute-28 completed_with_failures，A/B/C通过、static幻觉被event_static_evidence拒绝；4次¥0.00974288。temporal-v4-atom-8 completed_with_failures，B3事件（jump/下落歧义），C边界证据失败、static被拒绝；4次¥0.01037184。均qualityGate=null/unknown0/非账单。三次pilot加完整run本轮已知API估价¥0.0797378；旧Grok v3试验¥0.0075876另列，不重复计入。
- 工具receipt曾发现28个stdlib pyc漂移；仅从项目内固定SHA归档恢复这些文件，receipt/程序/DLL未改，完整init通过。始终env.ps1 + Python -B，禁止全局安装。

## 当前归属与下一步

root独占公共文档、UI/API、pilot、配置/存储/analysis和集成。temporal_frame_contract d026103已集成42604f9、workspace_launcher df475ef已集成0cc2c2f，worktree冻结；旧vision/pilot/workspace worktree也冻结，不覆盖root。两次只读复核未发现新增合同/兼容/安全缺陷，不是质量认可。

retrieval_negation在.worktrees/retrieval-negation、codex/retrieval-negation拥有仅application/retrieval.py、test_retrieval_negation.py、own sprint，正在修明确否定表述产生正向动作锚点的问题。不降低阈值，不改源事件，不写root。先核对worker提交/实际结果，再集成。

接续：完成并审查否定召回修正，记录版本与边界；复跑新Atom五查询三模式、播放/导出（篮子用至少3条移动查询，不能为测试硬凑跳跃数），完整verify/init；仅重启已核对health身份的本仓库服务；同步所有文档与Git。然后独立人评/更长动作与强模型对照，仍不能先转正式桌面/渲染/商业阶段。

恢复先读AGENTS、feature_list、shared workflow，检查git status/分支/文件归属、run状态、报告。素材/DB/模型在ignored目录，不随clone；配置更改创建新run，原run resume保留原prompt/预算/窗口。新分析显式config.temporal.example.json；默认config.example.json仍v2。密钥只使用现有进程DEEPSEEK_API_KEY，不打印/复制聊天密钥。每个实现/验证节点主动保存进度和Git检查点，不等额度提醒。
