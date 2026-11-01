# Sprint T11：全量 verify.ps1

**状态（2026-11-01）：已推送功能 2215cb3；docs 随后**

## 目标

跑通 scripts/verify.ps1（ruff format/check、mypy、pytest -W error、离线 wheel 双构建一致性、CLI help/version），修复失败项，记录墙钟耗时。

## 非目标

不递归清扫 .cache；不造大媒体；不下载需用户批准的东西；不 force push；不提交 .codex/agents/*.toml。

## 修复（最小）

1. **ruff**：若干源/测试文件 format 与 import 排序（含 cli/main.py、local_embeddings.py、多余空行）。
2. **mypy**：ui/server.py 企业审计导出分支局部名 `body/payload 与后续 timeline 分支冲突 → 改为 `audit_text/`audit_bytes/`audit_name/`audit_mime。
3. **pytest -W error / PowerShell GBK**：	ests/test_setup_media.py 的 invoke() 在 PYTHONUTF8=1 下对 Windows PowerShell 5.1 输出用 encoding="utf-8", errors="replace"，避免 _readerthread UnicodeDecodeError → PytestUnhandledThreadExceptionWarning。
4. **pytest -W error / 未关 socket**：多处 pytest.raises(HTTPError) / except HTTPError 未 close() 响应体，GC 时在无关测试里冒 ResourceWarning: unclosed <socket.socket>。已在 workspace/publication/clip/revision/narration/timeline/narration_script 等 HTTP 测试中关闭；	est_media_integration.py 同步 errors="replace"。

## Acceptance

- [x] verify.ps1 全绿
- [x] sprint 记录墙钟耗时
- [x] 文档同步；T11 ✅（docs 提交）

## Verification

`	ext
. ./scripts/env.ps1
# 墙钟（本机 Start-Process 包装）ELAPSED_SEC=1451.7（约 24.2 min）
# pytest：4487 passed, 5 skipped in 1438.75s
# Repeated offline wheel builds match:
# C73DB44FC66B6E98C8CCEA756B577EB2F4D93D59E6D213061CEF1985651D7A84
./scripts/verify.ps1   # EXIT=0
`

## 耗时

| 项 | 秒 |
| --- | --- |
| verify 墙钟 | **1451.7** |
| pytest 段 | 1438.75 |
| 结束时刻（Asia/Hong_Kong） | 2026-11-01 14:50:39 |

## 计数（源）

- feature_list product_features：51 · delivered 10 / partial 41 / 未开始 0 ≈60%；首产品 22 全 partial ≈50%
- tech-debt 表 21 行：resolved 14 / partial 2 / open 5
- human-inputs：现在必做 0；未来表 8 行
