# Sprint T9：反馈学习进一步（P042 编辑习惯）

**状态（2026-11-01）：已推送 origin/main bd294f3。**

## 背景

P042 已能：只读统计本机创作任务；按「做成成片次数」重排通用方案并写入 `ordering.renderedByPlan` / `localRenders`。
尚未：把常见**修改类型**反馈进新方案，且改时长必须可复现、不可静默。

## 设计（先于此实现）

### 目标

当本项目已保存修订的修改类型里，**裁剪**足够常见时，新生成的方案：

1. **建议更短镜头**：每个片段的成片时长上限改为 **1.0 秒**（`min(原模板帧数, fps)`，至少 1 帧）。
2. 在每个方案的 `advisories` 增加固定文案：`你常裁短，已建议更短片段`。
3. 把触发条件、观测计数与规则写入方案报告的 `ordering.editHabits`（及注册时冻结的输入文件），之后重跑同一任务只读冻结输入，不随后来历史漂移。

不改评分权重；不因统计失败而挡住生成方案（与现偏好统计相同）。

### 触发阈值（写进记录）

- `trimEdits = editKinds.get("裁剪", 0)`
- `totalEditEvents = sum(editKinds.values())`
- **applied** 当且仅当：`trimEdits >= 3` 且 `totalEditEvents > 0` 且 `trimEdits / totalEditEvents >= 0.5`

未达阈值：不改时长、不加该提醒；仍可在 `ordering.editHabits` 记下观测（若调用方传入了 editKinds）。

### 输入冻结（可复现）

方案任务注册时（与 `preferences.json` 同期）：

- 继续写 `input/preferences.json`：`planId → 成片次数`（v1 不变）。
- 新增写 `input/edit-habits.json`：
  `{ "schemaVersion": "creation-edit-habits-v1", "editKinds": {…} }`
  来源为当时 `feedback()` 的 `editKinds`；统计异常则写 `{}`。

Worker / `plan_creation(..., edit_kinds=)` 只读该冻结文件；无文件（旧任务）则 `edit_kinds=None`，行为与 T9 前一致（`ordering` 无 `editHabits` 键）。

### `ordering` 形状

```text
ordering.basis / ordering.renderedByPlan   # 保持现语义
ordering.editHabits.editKinds              # 冻结的类型计数
ordering.editHabits.trimSuggestion:
  applied, rule="max-output-seconds-per-segment=1",
  minTrimEdits=3, minShare=0.5,
  trimEdits, totalEditEvents, share
```

仅当调用传入 `edit_kinds`（含空 dict）时写入 `editHabits`；`None` 时省略，以兼容既有精确断言。

### 非目标

- 不跨项目汇总；不调用模型；不接支付/云。
- 不按「删镜头/变速/…」改结构或权重（本切片只做裁剪→更短片段）。
- 不做浏览器手点验收（单测锁合同）。

## Acceptance

- [x] 高裁剪占比：片段被 1s 上限裁短，advisories 含指定文案，`ordering.editHabits.trimSuggestion.applied is True`
- [x] 低占比/不足 3 次：时长与无 edit_kinds 时一致，applied False（若传入了 kinds）
- [x] 注册写入 edit-habits.json；重跑只用冻结输入
- [x] 旧 preferences 仅 int 映射仍可重排通用方案

## 已交付

- `creation_feedback.trim_suggestion` / `normalize_edit_kinds`；阈值：裁剪≥3 且占比≥50%。
- `plan_creation(..., edit_kinds=)`：applied 时每段 `min(帧数, fps)`，advisories 前插「你常裁短，已建议更短片段」；`ordering.editHabits` 记下 kinds 与规则。
- 方案任务注册冻结 `input/edit-habits.json`；worker 只读该文件。
- 测试：modes 裁短/跳过、feedback 阈值、jobs 冻结文件；相关 creation 回归通过。

## Verification

```text
pytest tests/test_creation_modes.py::test_edit_habit_trim_suggestion_shortens_records_and_skips_when_rare \
  tests/test_creation_modes.py::test_local_render_history_reorders_generic_structures_only \
  tests/test_creation_feedback.py::test_trim_suggestion_thresholds_and_normalize \
  tests/test_creation_jobs.py::test_plan_registration_freezes_edit_habits \
  -p no:cacheprovider --basetemp .cache/pt-t9 -q
```
