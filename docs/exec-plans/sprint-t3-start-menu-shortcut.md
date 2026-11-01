# Sprint T3：安装器可选开始菜单快捷方式

**状态（2026-11-01）：feature 待推送（docs 另记）。** `install-app.ps1 -StartMenuShortcut`（默认关闭）在开始菜单 Programs 下创建 `GamingCreator.lnk`（WScript.Shell，指向 `desktop/bin/GamingCreator.exe`）。路径写入安装记录 `startMenuShortcut`；卸载只删记录中的那个。测试用 `-ShortcutDirectory` 指向临时目录，不碰真实开始菜单。

## Acceptance

- [x] 默认不建快捷方式
- [x] `-StartMenuShortcut` 创建并记入 receipt
- [x] 升级不加开关时保留已记录快捷方式
- [x] 卸载删除记录的 `.lnk`
- [x] pytest 用临时 ShortcutDirectory

## Verification

```text
pytest tests/test_app_install.py -p no:cacheprovider --basetemp .cache/pt-t3 -q
```

## Non-claims

不写注册表；不默认改开始菜单；不宣称已做代码签名／干净机器验收。
