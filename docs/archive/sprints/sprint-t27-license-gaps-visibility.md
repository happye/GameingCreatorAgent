# Sprint T27：安装包 licenses／gaps 可见性（P039／T2）

**状态（2026-11-01）：已完成。**

## 目标

`build-app`／`install-app`（含 `-Smoke`）结束后**明确提示**阅读随包装入的：

- `licenses/THIRD-PARTY-NOTICES.md`
- `licenses/gaps.json`

**不**下载补许可；缺口仍靠人工确认（见 human-inputs／T2）。

## 非目标

- 不联网拉取 LICENSE
- 不自动“补齐” gaps
- 不宣称分发合规已完成

## 设计

### `scripts/license_visibility.py`

- `format_license_visibility(root) -> str`：给出绝对路径提示；若缺文件则警告；若 `gaps.json` 为列表则报告条数
- CLI：`python -B scripts/license_visibility.py --root <app>` 打印到 stdout
- 文案中文，含「不会联网下载补许可」「分发前请确认 gaps」

### 接线

- `build-app.ps1`：构建成功后打印；`-Smoke` 通过后再打印一次
- `install-app.ps1`：安装／升级成功后打印；`-Smoke` 通过后再打印一次
- 卸载路径不打印（无程序 licenses）

### 测试

- `tests/test_license_visibility.py`：路径／缺口条数／缺文件警告
- `tests/test_app_install.py`：夹具补 `gaps.json`；安装 stdout 含两文件名与提示关键词

### Acceptance

- [x] sprint 设计
- [x] 可见性提示＋无下载
- [x] build/install（Smoke）接线
- [x] 测试
- [x] P039 evidence 谨慎追加；文档；grok T27 ✅；下一＝T28
