# Sprint T2：第三方许可证随包材料

**状态（2026-11-01）：已推送 origin/main d1672f4（docs 另记）。** 便携应用打包时生成 `licenses/`：从本机已有 LICENSE/LICENCE/COPYING/NOTICE 与 dist-info `licenses/` 树、CPython `LICENSE.txt`、WebView2 `LICENSE.txt` 复制；汇总 `licenses/THIRD-PARTY-NOTICES.md`。缺正文的组件记入 `licenses/gaps.json` 与 `docs/exec-plans/human-inputs.md`，**不下载、不猜测**。

## 做法

1. `scripts/collect-third-party-notices.py`：收集并写出 notices／gaps。
2. `build-app.ps1`：打包时运行收集器到 `Output/licenses/`；`$programParts` 含 `licenses`。
3. `install-app.ps1`：`$programParts` 同步含 `licenses`。
4. 测试：每个打包用 dist-info 出现在 notices；缺 LICENSE 的出现在 gaps；脚本接线断言。

## 验收证据

- pytest：`tests/test_third_party_notices.py` + `tests/test_app_install.py`
- `build-app.ps1` 后 `dist/GamingCreator/licenses/THIRD-PARTY-NOTICES.md` 存在（866MB 包）。

## Non-claims

不代选 A／B／D；不标 F006；不宣称 GPL／模型／WebView2 分发已获用户确认。
