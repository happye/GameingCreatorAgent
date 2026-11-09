# 进度看板维护（所有 Agent：Codex / Claude Code / Grok）

看板：`docs/progress/index.html`（直接双击用浏览器打开，无需服务）。数据：`docs/progress/data.js`，由脚本从源文件生成，**不要手改 data.js 或 index.html**。

## 什么时候更新

做完一个模块、切片或修复，**且某个节点的状态或说明变了**时（功能实现推进、合同状态变化、流程试用、技术债开关、人工待办增减）。纯重构、测试或文档措辞不变状态时不更新。

## 怎么更新（两步，同一次提交）

1. 找到节点，只改那一处：

| 节点 | 改哪里 | 改什么 |
| --- | --- | --- |
| 51 项功能 P001–P051 的状态 | `feature_list.json` → `product_features` | `delivery_status` / `quality_status` / `release_status`（需证据，见 AGENTS） |
| 功能的“已有/还缺”说明 | `docs/progress/nodes.json` → `features.P0xx` | `done`、`todo`（各一句话）、`updated`（YYYY-MM-DD）、`sprints`（合同文件名） |
| 路线图批次 R1–R5、Q 与切片 | `nodes.json` → `roadmap[]` | 批次或切片的 `status`、`done`/`todo`；新合同在对应批次 `slices` 加一行 `{id,name,status,sprint}` |
| 总方案 6 阶段 | `nodes.json` → `stages[]` | `status`、`note` |
| Phase 0 检索验收 8 步 | `nodes.json` → `qualitySteps[]` | `toolReady`、`executed`、`note` |
| 端到端流程 J1–J3（主指标） | `docs/exec-plans/journeys.json` | 只在真实运行/用户试用后改 |
| J1 修复清单（试用反馈逐条） | `nodes.json` → `journeyFixes.J1[]` | 某条修好改 `status`/`note`；新一轮试用反馈换成新清单 |
| 上线前提（许可证、FFmpeg、Release、干净机、签名、J3、商用材料） | `nodes.json` → `releaseGates[]` | 满足一条改 `status: done` |
| 最近完整门禁 | `nodes.json` → `gate` | 每次 `verify.ps1` 结束改 `date/result/counts/merged/note` |
| 费用与授权 | `STATUS.md` “费用与授权”列表 | 已有规则，脚本直接读取 |
| 技术债 / 人工待办 | `tech-debt.md` 状态列 / `human-inputs.md` “仍待真实输入”表 | 已有规则不变 |
| 正在做 / 下一步 | `STATUS.md` “当前交付与下一步” | 里程碑或会话结束时（已有规则） |

`status` 只用：`done` 已完成 · `active` 进行中 · `partial` 部分 · `todo` 未开始 · `blocked` 受阻。

2. 运行 `python -B scripts/progress_ui.py`（任何 Python 3.11+，标准库，离线，约 1 秒），把 `data.js` 与源改动一起提交。同时生成的 `live.js`（生成时间、分支、最近提交）已 gitignore，不提交。

## 源格式约定（否则节点不显示或算错）

- 技术债状态列以 `resolved` / `partial` 开头才计为已解决/部分，其它都算未解决。
- 人工待办必须是 `human-inputs.md` “仍待真实输入”表里的一行。
- 合同关联编号（P0xx、R2-A、TDxxx）写在合同前 6 行；合同文件名 `sprint-*.md` 或 `grok-*.md`，新建后在 `roadmap` 对应批次挂一个切片，开工设 `active`，验收后 `done`。
- 功能“还缺”为空时自动用 `feature_list.json` 的 `remaining`，两处不必重复写。
- 旧手工看板 `docs/exec-plans/progress-board.md` 只保留标题计数（`status.py --check` 仍核对），日常以本看板为准。

检查：`python -B scripts/progress_ui.py --check` 在 data.js 过期、功能缺说明、合同未挂到路线图切片或状态值非法时退出 1。

## 省 Token 的做法

- 用编辑工具改一行 JSON，不要整文件重写 `nodes.json`；不要读 data.js。
- 新增 `sprint-*.md` 后，`--check` 会提示“未挂到切片”，按提示在对应批次加一行即可。
- 并行工作树合并时 `data.js` 冲突：直接重新运行脚本生成，不要手工合并。
- 数字（百分比、计数）全部由脚本计算；节点说明里不写数字口径，不把“工具就绪”写成“验收通过”。
