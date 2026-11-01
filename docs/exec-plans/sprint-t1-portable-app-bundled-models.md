# Sprint T1：便携应用内置本地 ASR／嵌入模型

**状态（2026-11-01）：feature 待推送（docs 另记）。** 安装版／便携目录现在自带语音识别与检索嵌入模型，装好即可分析新录像的语音并做本地检索，不必再依赖开发机 `.cache/models`。

## 做法

1. `app_paths.model_directory(repository, *parts)`：优先 `.cache/models/...`（开发），否则 `models/...`（安装）。
2. `_pinned_asr_settings` 与 `LocalEmbeddingProvider.from_manifest` 改走该 helper；清单哈希校验不变。
3. `build-app.ps1`：复制 faster-whisper／multilingual-e5-small → `Output/models/`，`.tools/native`，三份 pin 清单 → `Output/docs/references/`；`$programParts` 含 `docs`、`models`。
4. `install-app.ps1`：同步 `$programParts`；安装换入后把 `.venv/pyvenv.cfg` 的 `home` 指到**目标目录**内运行时（否则嵌入 worker 会失败）。
5. 验收：`build-app.ps1 -Smoke`；打包／安装目录内 Python 调 `from_manifest` 嵌入 `query: 测试`（384 维）+ `_pinned_asr_settings` 文件校验；临时安装后卸载。总大小 **866MB**＜1.5GB。

## 非宣称

不付费下载；不标 F006／F009／F010；不代选 A／B／D；不宣称真人质量／平台发布完成。

## Verification

```text
pytest tests/test_app_paths.py tests/test_app_install.py -p no:cacheprovider --basetemp .cache/pt-t1 -q
.\scripts\build-app.ps1 -Smoke
# 打包／安装目录：LocalEmbeddings.from_manifest + _pinned_asr_settings
```
