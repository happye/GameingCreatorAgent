# Sprint T12：用户手册（安装 → 发布包）

**状态（2026-11-01）：已推送功能 23c49b4；docs 随后**

## 目标

把 docs/references/creation-guide.md 扩成通俗中文端到端手册：从组装／安装到四平台本地预览包与沙箱发布。每步含 **入口 / 会发生什么 / 不会发生什么 / 常见问题**。

## 非目标

不发明付费／云／登录／真发布；不下载；不代选 A／B／D；不标 F006 通过；不改产品代码（纯文档）。

## 已写内容摘要

1. 便携 uild-app（models／licenses／不默认开始菜单）
2. install-app（-Destination／可选 -StartMenuShortcut／升级保数据／卸载）
3. 启动工作台（EXE／Start-Workspace）
4. 准备录像与 Free 月度约 60 准备分钟（接受时记账）
5. 分析前置诚实边界
6. 模板方案／活动规则（Free 不含）
7. 剪辑／字幕／配乐／变速／转场
8. 渲染与 Free 水印「GamingCreator Free」
9. 封面文案 → 四平台本地包 → 项目团队审核／审计导出／沙箱发布
10. 套餐表与附录 CLI／人工 0／licenses gaps

## Acceptance

- [x] creation-guide 覆盖安装→发布包，每步四段结构
- [x] 与当前产品一致（水印、准备分钟、StartMenu 可选、licenses）
- [x] 文档同步；T12 ✅；推送

## Verification

`	ext
# 人工通读 docs/references/creation-guide.md 标题与四段结构
# 对照 entitlements.PLANS / install-app.ps1 / human-inputs
`
