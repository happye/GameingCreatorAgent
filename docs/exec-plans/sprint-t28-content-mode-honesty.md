# Sprint T28：内容模式诚实文案（P043–P049）

**状态（2026-11-01）：已完成。**

## 目标

各内容模式的方案卡／帮助文案统一写明：

> 描述代理评分、非画面理解／未做人评／投放未验证

并与 `docs/references/creation-guide.md` 交叉链接。不下载、不付费视觉、不宣称 F006／人评通过。

## 非目标

- 不改模板取材算法
- 不做人评、不验投放
- 不把 P043–P049 或 F006 标成完成／passes=true

## 设计

### 共享文案

`creation_modes.MODE_HONESTY_SHORT`／`MODE_HONESTY_HELP`／`CREATION_GUIDE_REL`

### 接线

- `creative_planner`：内容模式推荐方案带 `honesty`；结果顶层带 `modeHonesty`（`understandingVerified` 仍为 false）
- `/creation`：页头、内容类型旁 `#mode-honesty-help`、方案区 `#plans-honesty`、推荐方案卡 `.mode-honesty`
- `creation-guide` 第 6 节与文首诚实边界写入同一句，并说明工作台对照位置
- 顺带修复知识库保存路径上预先存在的 `} } catch` 语法错误（否则整个 creation.js 无法解析，浏览器文案测试无法跑）

### 测试

- `tests/test_mode_honesty.py`：常量、指南含句、七模式推荐方案均带 honesty
- `tests/test_creation_copy_browser.py`：页头／帮助／方案卡严格路由文案
- 相关 `test_creation_modes` 回归

### Acceptance

- [x] 统一诚实句
- [x] creation-guide 交叉链接
- [x] pytest／strict-route 浏览器文案测试
- [x] P043–P049 evidence 谨慎追加；F006 不动
- [x] 文档；grok T28 ✅；清单 T1–T28 已尽
