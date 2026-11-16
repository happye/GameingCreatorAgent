# 阶段 C：替换镜头与图层本机草稿 v3

R2 / 阶段C · P032、P040 · 2026-11-17 · 已集成，受影响验证闭合，待本批完整检查。

基线：1929c88。实施树：`.worktrees/draft-replacements-overlays`。实现提交55886b4；唯一task_quality_guard增量审查通过，无未闭合P1/P2。未宣称人评/发布验收完成。

## 固定范围

沿原 work/project/job/plan 存储地址和 whole-file SHA256，增加 `studio-clip-draft-v3`：在 v2 字段上加入 `candidateManifestSha256`（无清单时 null）、`replacements:[{targetClipId,candidateId}]`、`overlays:{schemaVersion:'creation-overlays-v1',items:[选择字段]}`。仅保存仍存在镜头的替换，绝不保存素材对象、URL、文件路径或证明。临时无效图层（含 NaN 数字）保留上次可恢复数据并标 partial。

v1/v2 原路径读取、恢复时不迁写；下一次真实编辑写 v3。候选面板只读加载不算编辑。manifest 进入编辑 state 和 undo snapshot，恢复后不打开面板也能保存。新替换不再因父镜头旧坐标而被本地范围检查误拒。

沿现有 draft-restore-preview，只读 load_chain 验 project/parent receipt，prepare_revision/manifest_for_chain 验真实清单和 revision-v4，按新输出 frames 验图层及资产回执，音轨/字幕沿既有路径。旧精确 8 字段请求保持原 4 字段响应；完整新增 3 字段才返回公开 clips/bounds/replacements/manifest/overlays/overlayAssets。候选公开路径/时钟投影复用 replacement_jobs helper；不添加 API。

全部成功后一次 edit 原子应用。保留 restoreEpoch/editEpoch、scope、receipt、raw hash、live task 门。每次 await 后复核；取消、丢弃、undo/reset、新 restore 和切 scope 不接受迟结果。候选异步响应也核 loading/base。恢复不生成 job、旁白、模型调用、证据、账单或人工标签。

## 验收与具名检查

- `tests/test_creation_draft_restore.py`：v3 跨源投影与真实 v4 保存、v4 父再替换、坏 manifest/candidate/范围、图层 receipt/时长整份拒绝；父 v4 无新替换仍要求 manifest；旧精确响应不变。文件字节全盘对比确保恢复只读。
- `tests/test_studio_clip_drafts_browser.py::test_v3_cross_source_overlay_narration_refresh_undo_save`：跨源替换、裁剪、图层、已存在本机旁白；刷新手动恢复、不打开候选面板、undo/redo 后发出真实保存请求并由真实服务读回。
- `test_v3_out_of_duration_overlay_keeps_last_valid_snapshot`（超尾/裁短后保留合法快照）、`test_v3_replacement_caption_target_maps_for_projection_save_and_replay`（手写/空串字幕）、`test_legacy_snapshot_candidate_read_does_not_migrate`、`test_nan_overlay_preserves_last_recoverable_snapshot`、`test_late_candidate_catalog_cannot_cross_work_scope`：原字节保留、临时非法输入与候选迟到隔离。
- 既有 `test_slow_projection_cannot_land_after_new_intent` 与本文件其他恢复/取消回归继续适用。

## 本树验证

Ruff check/format（3 Python 实现 + 2 测试文件）、mypy（3 实现文件）、node --check（2 JS 文件）通过。pytest 由主 Agent 追加授权独占执行，全部显式 `--override-ini=pythonpath=src`，实际 import 已核本树源码。

- 首轮两具名文件：`.cache/test-logs/pytest-20261116-203220.log`，63 过、1 失败；失败为新增综合 browser 夹具 PNG 注册寻找临时目录 ffmpeg，不代表业务恢复通过。修夹具到项目工具绝对路径。
- 两处审查修复后原失败与新增受影响节点：`pytest-20261116-203707.log`，8 过；涵盖真实跨源+裁剪+图层+已有本机旁白刷新恢复、无需候选面板保存、undo/redo、手写/空串字幕、超尾/裁短、NaN/partial 和旧响应。
- 字幕省略继承及坏形状/重复/未知身份：`pytest-20261116-203852.log`，定向通过。保留原始请求字节，省略 overrides 时继承/过滤语义不变；仅显式字幕经已验证 v4 目标→新身份映射，投影反向映射保持本次 target 身份。

工作树 .venv/.tools 缺失，已按授权建立指向主树的 junction，未安装依赖。最初 env.ps1 回落全局 Python 导致 ruff missing；建立 junction 后相同静态命令通过。无付费、上传、发布。

## 主树集成与字幕组合修复

主树15文件受影响检查：257过1失败（test-affected-20261116-204238.log），旧test_v4_replacement_draft_and_stale_manifest仍断言拒绝target字幕，现改验可信映射及未知身份拒绝。另修subtitle_preview的reserved比较，将request target按可信v4映射到新ID，避免开启逐词高亮时隐藏字幕复活；手写字幕同样保留。唯一task_quality_guard增量静态通过，无未闭合P1/P2。

独立树首轮002205仍有上述旧断言失败；修后两文件20过（pytest-20261117-002310.log），Ruff/格式/mypy通过。主树修后原失败及隐藏/手写×sidecar/burn组合5过（pytest-20261117-002420.log）；257项既有通过证据保留。下一步仅本批完整verify一次，未Release；不将历史失败记录改绿。
