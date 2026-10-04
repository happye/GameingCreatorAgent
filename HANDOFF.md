# 当前交接

更新时间：2026-10-04（Asia/Hong_Kong）。Codex、Claude Code、Grok Build 共享此恢复入口；历史见 `progress.md`，验收见 `feature_list.json`。

## 当前结果与版本

F007本地检查工作台已交付，本轮F008进一步完成固定桌面布局、预览/时间轴/篮子同屏、列表滚动保持和按源时间选片排序。既有能力：项目/run选择、原视频播放与区间结束暂停、证据图/音频与转录、描述/标签筛选、阶段/费用、按run隔离的片段篮、JSON/CSV区间清单。新视频仍用CLI分析；页面不触发付费分析、不生成MP4、不发布或结算。

F000–F005、F007、F008技术合同已验收；**F006独立人工U10仍false**。用户明确授权本地检查交互，依据ADR-002；正式桌面/商业阶段仍有原质量门槛。

已验证代码87637af已普通快进同步并推送origin/main和origin/codex/workspace-usability；root当前main，后续交接文档提交见git log。工作检查点1684587/decf5b2已保存；HTML/CSS worker5a44dfd/7ad1321已集成1bf8881/600276e，root最终字体/比例/canvas与排序回归通过。计划/证据见sprint-workspace-usability，全部本轮worker已冻结。不要从历史worktree覆盖root。

本轮GitHub443间歇连接失败，重试已成功完成最终推送，不改全局Git。最终新版可直接刷新8765页面：桌面各面板内滚动，源预览/时间轴/篮子同时可见；源码由main提供，最新页面HTTP200且含片段篮面板。F006是内容评级0/1/2/3、每主查询前十槽≥7独立可用事件，见human-acceptance-guide；本地混合推理与未来EXE见deployment-roadmap，当前并非全离线/已打包EXE。

## 直接使用

在仓库根目录PowerShell：

```powershell
./scripts/run-ui.ps1
```

浏览器打开 `http://127.0.0.1:8765/`，选 `demo-phase0` 和 `f76f5d6495314c04ae04083614d4afd6`；输入「寻找角色打斗和攻击的片段」，候选条数3。点击候选预览、证据缩略图放大，点+选片并下载JSON/CSV。刷新后默认首个Completed run；重新选同一run可恢复其片段篮。另一个Completed run c6d93b984f374cd4aa755ed0c81e4d73不是此次真实PV验证对象。

新机先 `./scripts/setup-demo.ps1`，另备固定FFmpeg；本机可用 `-Offline`。素材、DB、权重不随Git克隆。完整步骤见user-manual和demo-quickstart；CLI新分析用run-demo的-Video和进程密钥。

## 最新验证

- `./scripts/verify.ps1`退出0：**582 passed、1 skipped（33.37s）**；Ruff73文件、mypy48源文件、CLI及两次离线wheel通过。跳过项为Windows文件symlink权限，独立canonical-path回归已通过。
- wheel SHA256：`36405a6c8f3b3ba88107db7d54d8fbe6bd253254a856a9fa0ac05b9d8a093b17`；50条目含全部3个静态资源，无模型、DLL、视频、DB或缓存。
- 项目内Chromium153.0.8010.12真实PV中文/英文各验证通过：111事件、3候选，实际rank1播放并自动停在结束（中文28–29s停29，英文此次31–32s停32），真实证据加载、JSON/CSV身份/微秒/证据、筛选不改排名、汽车维修hybrid空结果、同run篮子恢复、无JS错误。最新报告在ignored `artifacts/workspace-usability-validation/` 和英文目录；另验证两桌面视口无页面滚动、深列表预览/选择位置保持、乱序选3段后篮子/存储/JSON/CSV统一时间顺序及恢复3段。检索rank保留，不能由导出第一段反推；390px仅验无横向溢出，未声明手机同屏。旧初版记录不覆盖历史判定。
- 前端worker21项合成浏览器交互检查通过（含跨run响应隔离、恶意文本、CSV防公式注入、转录、390px布局）。范围和局部报告位置见sprint-inspection-frontend。
- 五项用户/系统环境及Python注册表指纹未变；这是指定边界检查，不是全系统监控。本轮没有付费API请求。
- Windows服务使用独占端口，重复启动不再与旧页面同时监听；仅停止两项已核对本仓库命令行的旧UI进程。最终8765只剩一个监听，projects/inspect已返回新版111事件、videoUrl和费用字段。

## 已有真实分析与质量边界

完成run f76f...：漫画群星PV95.175874s、24窗口/111事件/0转录，API费用估算¥0.06246088，非账单。旧失败run823799e10a0440e8aec8b78b603bec57：2/24窗口、10事件、schema拒绝，估价¥0.01163912；旧响应未保存，不能补称失败字段。两次原分析估价合计¥0.0741。

中文与英文攻击hybrid均返回28–29、31–32、30–31s；英文仅加有限attack/fight词法映射，并非通用翻译。汽车维修hybrid为空，pure semantic仍有误召回。开发报告qualityGate=null；未标注benchmark退出6是预期，不能由Agent代替独立人工标签。

## 下一步与恢复规则

1. 先核对 `git status --short`、当前分支及远端状态，再按以下剩余事项新建任务。当前交付已普通快进同步main，工作台8765已启动；会话/电脑关闭后用run-ui.ps1重新启动，不依赖Agent内存中的进程号。
2. 后续优先F006：冻结独立录制会话和主/稀疏/负例人工标签，再校准召回/动作边界。已有4开发视频490.693314s且有同源分组，不等于10–20独立会话或小时级验收。
3. TD001：长媒体showinfo/ashowinfo16MiB上限；TD005：1024文本请求上限（查询占1，最多1023文档）及长索引；TD006：非零PTS、不同音视频起点的浏览器currentTime映射/编码支持尚未验证。保持E5固定batch=1的空间身份和稳定性。
4. 正式桌面、Creative Planner、MP4渲染/发布另立工程任务，勿以F007替代F006门槛。

全部工具/包/模型/缓存仅在.tools/.venv/.cache；可选Playwright在ui-test extra，浏览器在.tools/browsers，不需要系统安装。密钥只走进程DEEPSEEK_API_KEY，不复制聊天密钥或写文档。开始会话读AGENTS、HANDOFF、feature_list和共享workflow，核对分支/未提交归属；旧scratch/worktrees冻结，不覆盖当前root。每个实现/验证节点主动更新sprint/交接并保存Git检查点，不等额度耗尽。
