# Gaming Creator Agent

本地优先的游戏内容创作工具：把本机游戏录像分析成语义时间线，用一句话找片段，再按模板生成成片、字幕、封面文案和各平台发布包。视频不离开本机；只有经你授权的视觉分析才会调用云端模型。

**当前进度看 [`STATUS.md`](STATUS.md)。**一句话概括：工程上主流程已能跑通，但你亲自试过、判定可用的端到端流程目前是 0 条，Phase 0 检索质量验收（F006）仍待人评。

## 快速开始

在仓库根目录打开 Windows PowerShell：

```powershell
./scripts/setup-demo.ps1 -Offline   # 准备项目内的运行时、依赖和模型（要求缓存已在本机）
./Start-Workspace.cmd               # 打开本地工作台；启动不触发任何付费分析
```

工作台里可以：
- 预览录像和证据；
- 多录像检索（一句话找片段）；
- 在“创作视频”里选模板生成方案，渲染 MP4，编辑字幕、旁白和配乐；
- 生成封面文案和 B 站等平台的本地发布包。

打包和安装（只装到当前用户目录，不写注册表）：

```powershell
./scripts/build-app.ps1             # 组装便携版到 dist/GamingCreator
./scripts/install-app.ps1           # 安装或升级到 %LOCALAPPDATA%\Programs\GamingCreator；-Uninstall 卸载
```

## 文档地图

| 你想… | 看这里 |
| --- | --- |
| 新工作台（预览） | 打开 http://127.0.0.1:8765/studio ：深色剪辑软件式界面，逐步替换旧页面，见 [studio sprint](docs/exec-plans/sprint-studio-workbench.md) |
| 用工具做视频 | [10 分钟上手](docs/references/quickstart-10min.md)，更多功能见[创作全流程手册](docs/references/creation-guide.md) |
| 分析、检索、验收的命令行用法 | [使用手册](docs/references/user-manual.md)、[Demo 快速开始](docs/references/demo-quickstart.md) |
| 了解你需要做什么 | [人工待办](docs/exec-plans/human-inputs.md) |
| 看量化进度 | [`STATUS.md`](STATUS.md)、`python -B scripts/status.py`、[进度看板](docs/exec-plans/progress-board.md) |
| 产品方向 | [总方案](游戏内容创作与商业化产品总方案%20V1.0.txt)、[加速路线](docs/exec-plans/accelerated-product-roadmap.md) |
| 架构和设计决定 | [`docs/design-docs/`](docs/design-docs/) |
| 开发规则（Agent 和人通用） | [`AGENTS.md`](AGENTS.md)、[测试指南](docs/references/testing-guide.md) |
| 历史记录 | [`docs/archive/`](docs/archive/)、`progress.md`、git 记录 |

## 边界

- 录像、密钥、数据库、生成的媒体都不进 Git。
- 付费视觉分析每月有 ¥50 预授权，只能用于你指定的素材；超出部分每次单独询问。
- 已有的标注和付费结果都会保留，不会自动重跑。长钟馗的分析已经结束，不要重跑它的 launcher。
- “沙箱发布”只在本机模拟，不会上传；“套餐与用量”只是本地开关，不涉及支付。

仓库：[happye/GameingCreatorAgent](https://github.com/happye/GameingCreatorAgent)
