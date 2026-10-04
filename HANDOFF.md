# 当前交接

更新时间：2026-10-04（Asia/Hong_Kong）。Codex、Claude Code、Grok Build 共享此恢复入口；历史见 `progress.md`，验收见 `feature_list.json`。

## 当前任务：Grok复核与可测试版本

Codex已将Grok全部未提交集成保存为4c37a63（codex/temporal-gameplay），不回滚其实现或实验。只读复核确认费用/失败记录一致；v3旧响应未保存，无法断言具体坏端点。当前改用独立v4合同：模型选起止frame alias，程序用源时钟生成半开区间；保留v1/v2/v3内容/hash。root已接入配置/SQLite/analysis/pilot新版本，并新增/api/health；对应配置/pilot/HTTP定向检查通过，暂未新API调用。F006/F009仍false。

活动worker：temporal_frame_contract在.worktrees/temporal-frame-contract拥有deepseek_vision.py/new test/own sprint；workspace_launcher在.worktrees/workspace-launcher拥有Start-Workspace.cmd、scripts/start-workspace.ps1、真实PowerShell生命周期测试/own sprint。都不得回写root其他文件。旧temporal-vision/pilot及全部历史scratch冻结。

下一步先集成两个worker独占提交；root更新旧测试“v4 unsupported”为v5，生成最新config.temporal.example的v4实际hash。运行针对合同/脚本检查，然后先同0–4秒有限对照，再28–32秒动作窗口及同帧control；成功且内容合理后才新完整run。旧run不会因改代码变成新理解。一键启动仅打开本地工作台，不自动收费或重新分析。最后完整verify、真实浏览器/启动器复核、公共记录与Git推送；未完成不称已修好。

pytest初次使用嵌套basetemp未建父目录导致setup错误，创建独立.cache/pytest-runs目录后恢复；媒体stat回归在粗粒度时钟下两个同大小写入mtime不变，测试显式变更本地fixture mtime验证已有缓存失效合同，不改变生产缓存。该缓存依赖文件元数据变化，不能声称能检测元数据完全不变的外部篡改。

## Grok集成与实验复核（历史基线）

**2026-10-04最新用户验收：F006玩法检索未通过。** 用户反馈打Boss、跳跃、射击找不到。本轮只集成时序分析合同，并完成一个四秒窗口的开发对照；这些查询没有修好。禁止把3条PV攻击候选或这次模型输出当玩法质量证据。`feature_list.json` 里 F006 与 F009 都保持 `passes: false`。

当前分支 `codex/temporal-gameplay`，HEAD 仍是 `e124abc`，集成改动未提交、未推送。root 已接入 temporal-vision 的 `deepseek_vision.py` 与 `tests/test_temporal_vision.py`（`bdf3861` 加上仅格式化的工作区差额），以及 temporal-pilot 的 `scripts/validate-temporal-gameplay.py` 与 `tests/test_temporal_pilot.py`（`ca45f1d`）。没有拷贝两个 worker 的 sprint，也没有用 worktree 覆盖 root。`config.example.json` 未改，v2 hash 仍是 `f9adb61a5be1dd03ca603c9515c5f6ffea3ae731b1f55a61332a23dd37383236`。新 `config.temporal.example.json` 为 500ms 采样、9 帧、重叠 2 帧，`promptHash` 是已交付 `phase0-vision-v3` 的真实 SHA-256：`27762b0b9d390c64d53ec4be815bd6e8ead4d249ec9864bb87735223b3ad1c4d`。Provider 对外 `max_images` 为 9；v1/v2 请求仍最多 5 张，旧 prompt hash 未变。

开发对照用本地《漫画群星：大集结》PV，sha256 `e4ad1f974910639b7914fec1b668e6cbea3d331721b08b56268ee548f8b7619a`。两次不带 `--execute` 的目录是 `artifacts/temporal-gameplay-dry-1` 与 `artifacts/temporal-gameplay-dry-2`：状态都是 `frozen`，`executed` false，`qualityGate` null，采样 `1/2`，source sha256 相同。A 是 v2 每隔一帧的 5 张，B 是同一 0–4 秒的 v3 全部 9 张，另有静帧复制和倒序输入。两次 invocation 都为空，没有 provider HTTP。倒序是本地输入拒绝，不是反向播放理解证据。

一次未提高脚本默认费用和请求上限的 `--execute` 写到 `artifacts/temporal-gameplay-execute-1`，进程退出码 4，报告 `completed_with_failures`，`qualityGate` null。window-0-A（v2）completed，5 条事件，估价 ¥0.0022108。window-0-B（v3）失败，`provider.schema` / `evidence_outside_range`，0 条接受事件，估价 ¥0.003524。static-B completed，0 条事件，`temporalControlPassed` true，没有确认连续动作。reversed-order-B 在发送前返回 `provider.input`，`cost_cny` 为 null，`cost_status` 为 unverified。三次已发送调用的已知估价合计 ¥0.0075876，`billingConfirmed` false，不是账单。密钥没有写入报告。

下一条工作：查看 `artifacts/temporal-gameplay-execute-1` 里 window-0-B 的 `evidence_outside_range` 拒绝，收紧 v3 提示让被引用帧落在半开区间内，先用离线视觉测试证明，再对同一个四秒窗口重跑一次有界 `--execute`。不要全量重分析 PV，不要把 F006 或 F009 标成通过，不要宣称打Boss、跳跃或射击已经修好。

上一轮F007/F008本地检查工作台已交付固定桌面布局、预览/时间轴/篮子同屏、列表滚动保持和按源时间选片排序。既有能力：项目/run选择、原视频播放与区间结束暂停、证据图/音频与转录、描述/标签筛选、阶段/费用、按run隔离的片段篮、JSON/CSV区间清单。新视频仍用CLI分析；页面不触发付费分析、不生成MP4、不发布或结算。

F000–F005、F007、F008技术合同已验收；**F006独立人工U10仍false**。用户明确授权本地检查交互，依据ADR-002；正式桌面/商业阶段仍有原质量门槛。

上一轮已验证代码87637af与收尾文档317b22d已同步origin/main；origin/codex/workspace-usability保留87637af。HTML/CSS worker5a44dfd/7ad1321已集成1bf8881/600276e，上一轮worker冻结。计划/证据见sprint-workspace-usability；本轮改动仅在codex/temporal-gameplay，不从历史worktree覆盖root。

上一轮 F008 页面记录曾提到 GitHub 443 后的重试；本轮时序改动没有推送，远端状态以 git 为准。F008 页面仍是：桌面各面板内滚动，源预览/时间轴/篮子同时可见。F006 是内容评级 0/1/2/3、每主查询前十槽至少 7 个独立可用事件，见 human-acceptance-guide。本地混合推理与未来 EXE 见 deployment-roadmap，当前并非全离线或已打包 EXE。

## 直接使用

在仓库根目录PowerShell：

```powershell
./scripts/run-ui.ps1
```

浏览器打开 `http://127.0.0.1:8765/`，选 `demo-phase0` 和 `f76f5d6495314c04ae04083614d4afd6`；输入「寻找角色打斗和攻击的片段」，候选条数3。点击候选预览、证据缩略图放大，点+选片并下载JSON/CSV。刷新后默认首个Completed run；重新选同一run可恢复其片段篮。另一个Completed run c6d93b984f374cd4aa755ed0c81e4d73不是此次真实PV验证对象。

新机先 `./scripts/setup-demo.ps1`，另备固定FFmpeg；本机可用 `-Offline`。素材、DB、权重不随Git克隆。完整步骤见user-manual和demo-quickstart；CLI新分析用run-demo的-Video和进程密钥。

## 最新验证

- `./scripts/verify.ps1`退出0：**618 passed、1 skipped（34.28s）**；Ruff 76 文件、mypy 48 源文件、CLI 及两次离线 wheel 通过。跳过项仍是 Windows 文件 symlink 权限；canonical-path 回归通过。检查页 HTTP 测试改为不走进程代理，避免 `HTTP_PROXY` 把回环请求变成 502。
- wheel SHA256：`b37b039a4c8688d9320b0bd8a29521306d57a970c26900660f951e679938f52f`；仍是 50 个条目。示例配置和 pilot 脚本不在 wheel 内。
- 时序定向测试 151 passed（`test_deepseek_vision.py`、`test_temporal_vision.py`、`test_temporal_analysis.py`、`test_temporal_pilot.py`，`-W error`，缓存目录在 `.cache/pytest-runs`）。v1/v2 仍拒绝第 6 张图，对外上限是 9，v3 拒绝倒序、重复时间、复制图动作声明和单帧动作声明，旧 prompt hash 未变。
- 磁盘复核：`config.temporal.example.json` 的 promptHash 等于已交付 `vision_prompt_fingerprint("phase0-vision-v3")`，同为 `27762b0b9d390c64d53ec4be815bd6e8ead4d249ec9864bb87735223b3ad1c4d`；`git diff -- config.example.json` 为空。root 上存在 `deepseek_vision.py`、`tests/test_temporal_vision.py`、`scripts/validate-temporal-gameplay.py`、`tests/test_temporal_pilot.py`。`artifacts/temporal-gameplay-dry-1` 与 `dry-2` 的报告都是 `frozen`、executed false、qualityGate null、invocation 0，source sha256 都是 `e4ad1f974910639b7914fec1b668e6cbea3d331721b08b56268ee548f8b7619a`。`artifacts/temporal-gameplay-execute-1` 是 `completed_with_failures`、executed true、qualityGate null；static-B 的 `temporalControlPassed` 为 true 且事件数为 0。
- 项目内Chromium153.0.8010.12真实PV中文/英文各验证通过：111事件、3候选，实际rank1播放并自动停在结束（中文28–29s停29，英文此次31–32s停32），真实证据加载、JSON/CSV身份/微秒/证据、筛选不改排名、汽车维修hybrid空结果、同run篮子恢复、无JS错误。最新报告在ignored `artifacts/workspace-usability-validation/` 和英文目录；另验证两桌面视口无页面滚动、深列表预览/选择位置保持、乱序选3段后篮子/存储/JSON/CSV统一时间顺序及恢复3段。检索rank保留，不能由导出第一段反推；390px仅验无横向溢出，未声明手机同屏。旧初版记录不覆盖历史判定。
- 前端worker21项合成浏览器交互检查通过（含跨run响应隔离、恶意文本、CSV防公式注入、转录、390px布局）。范围和局部报告位置见sprint-inspection-frontend。
- 五项用户/系统环境及 Python 注册表指纹未在本轮复查。上面的 `--execute` 是本轮唯一付费调用，估价已写入实验报告，未对账单。
- Windows服务使用独占端口，重复启动不再与旧页面同时监听；仅停止两项已核对本仓库命令行的旧UI进程。最终8765只剩一个监听，projects/inspect已返回新版111事件、videoUrl和费用字段。

## 已有真实分析与质量边界

完成run f76f...：漫画群星PV95.175874s、24窗口/111事件/0转录，API费用估算¥0.06246088，非账单。旧失败run823799e10a0440e8aec8b78b603bec57：2/24窗口、10事件、schema拒绝，估价¥0.01163912；旧响应未保存，不能补称失败字段。两次原分析估价合计¥0.0741。

中文与英文攻击hybrid均返回28–29、31–32、30–31s；英文仅加有限attack/fight词法映射，并非通用翻译。汽车维修hybrid为空，pure semantic仍有误召回。开发报告qualityGate=null；未标注benchmark退出6是预期，不能由Agent代替独立人工标签。

## 下一步与恢复规则

本轮接续以顶部“当前任务”为准：v4帧边界合同、诊断、有限实测与一键启动。Grok原建议收紧v3提示仅是假设；旧响应没有具体错误值，不改写历史为已查明原因。F006仍未通过，内容实测前不全量重分析。

恢复时先核对 `git status --short`、当前分支和未提交文件归属。F008 已在 main；本轮时序改动尚未提交，不要未经验证推 main。工作台 8765 可继续用旧结果；关闭后用 `run-ui.ps1` 重新启动。独立人工 U10、TD001/TD005/TD006、正式桌面、Creative Planner、MP4 渲染和发布都不是这件下一条工作。开发素材及这次四秒对照不等于 10–20 个独立会话。

全部工具/包/模型/缓存仅在.tools/.venv/.cache；可选Playwright在ui-test extra，浏览器在.tools/browsers，不需要系统安装。密钥只走进程DEEPSEEK_API_KEY，不复制聊天密钥或写文档。开始会话读AGENTS、HANDOFF、feature_list和共享workflow，核对分支/未提交归属；旧scratch/worktrees冻结，不覆盖当前root。每个实现/验证节点主动更新sprint/交接并保存Git检查点，不等额度耗尽。
