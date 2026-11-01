# Sprint T21：本机知识库目录导入（P018）

**状态（2026-11-01）：已完成（待 SHA）**

## 目标

选定本机文件夹，**批量**导入 txt／md（可选截图／PDF）为游戏知识条目；每条带来源说明；**不联网抓取**。

## 非目标

- 不爬 Wiki／不下载
- 不自动改创作引用策略
- 不递归整盘；不做付费 OCR 云端
- 不宣称 F006／人评

## 设计

### 导入合同

| 项 | 规则 |
| --- | --- |
| 路径 | 本机绝对／相对目录；拒绝符号链接；仅一层直属文件 |
| 默认后缀 | `.txt` `.md` |
| 可选媒体 | `.png` `.jpg` `.jpeg` `.bmp` `.pdf`（复用 `read_rule_source`，OCR 标注进来源说明） |
| 上限 | 每批最多 50 个文件；单文件 ≤10MB（与规则读取一致）；正文仍 ≤20000 字 |
| 标题 | 文件名（去后缀），截断到 100 字 |
| 来源 | `sourceKind` 用户所选；`sourceLabel` = 用户来源说明 + `目录导入` + 相对文件名；OCR／部分页按既有知识文件逻辑追加 |
| 存储 | 逐条 `KnowledgeStore.add`；内容重复（同 entryId）记 `skipped`；单条失败不中断批次 |

### 入口

- `application/knowledge_import.py`：列举／导入纯逻辑
- POST `/api/knowledge-import`：`{game,directory,sourceKind,sourceLabel,includeMedia?}`
- CLI `import-knowledge`
- 创作页知识面板：目录路径 +「含截图／PDF」+「从目录导入」

### Acceptance

- [x] sprint 设计先于实现
- [x] 导入模块 + CLI／API／UI
- [x] 测试：txt／md 批量、可选媒体开关、重复跳过、链接拒绝
- [x] P018 evidence；文档；T21 ✅