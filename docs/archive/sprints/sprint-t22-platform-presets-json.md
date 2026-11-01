# Sprint T22：平台规格 JSON 化（P034）

**状态（2026-11-01）：已完成（0cff287）**

## 目标

把抖音／快手／B站／小红书本地导出限值／尺寸规格，纳入**版本化 JSON 清单加载**并补测试；页面仍可编辑覆盖；**不宣称官方已核**。

## 非目标

- 不联网拉取官方规则、不写“已核对官方文档”
- 不改发布／支付／F006
- 不强制填入伪官方限值数字（现有 null＝`not_configured` 语义保留）

## 现状

`infrastructure/platform_presets/{bilibili,douyin,kuaishou,xiaohongshu}.json` 已存在；`package_jobs.profiles()` 直接读文件。缺：manifest 版本合同、集中加载器、加载回归测试。

## 设计

### Manifest

`platform_presets/manifest.json`：

- `schemaVersion`: `platform-presets-v1`
- `disclaimer`: 明确 local_preset／非官方／未核验
- `ruleVersion`: 与各预设 `RuleVersion` 一致（`local-v1`）
- `platforms`: 有序四平台 id

### Loader

`infrastructure/platform_preset_loader.py`：

- 读 manifest → 按序加载 `<id>.json` → `validate_profile`
- 校验每份 `Platform`／`RuleVersion`／`Source.kind=local_preset`
- `load_platform_profiles(root=None) -> list[dict]`
- `package_jobs.profiles()` 改走 loader

### 覆盖

创作页既有编辑：改 Fields 后追加 `RuleVersion=…-edited-…`；预设文件不被写入。

### Acceptance

- [x] sprint 设计先于实现
- [x] manifest + loader + profiles() 接线
- [x] 加载／诚实 Source／编辑覆盖测试
- [x] P034 evidence 谨慎追加；文档；T22 ✅