# Sprint T20：detect-shots 夹具回归（P010）

**状态（2026-11-01）：已完成（待 SHA）**

## 目标

扩大**合成**黑场／硬切夹具并做回归；工作台与报告旁路文案标明「抽检未人评」。不做人评结论、不宣称准确率达标。

## 非目标

- 不改 scdet／blackdetect 阈值（未人评校准）
- 不按镜头重切分析窗口、不付费视觉、不 F006
- 不生成大媒体（分辨率与时长受限，单文件字节上限，测完即删）

## 设计

### 夹具

- `tests/fixtures/shot-hard-cases/catalog.json`：案例 id、片段序列（颜色／时长）、期望 cuts／black 数量与时间容差
- `tests/shot_hard_case_fixtures.py`：按 catalog 用本机 FFmpeg concat 合成小 MP4；`maxVideoBytes` 硬上限
- `tests/test_shot_hard_cases.py`：catalog 诚实性；真 FFmpeg 检测回归；测后删除

### 文案

- 报告 `notes`、工作台 `shot-summary` 及相关旁路：显式「抽检未人评」；保持 `humanReviewed: false`

### Acceptance

- [x] sprint 设计先于实现
- [x] 扩大合成夹具 + 回归
- [x] 工作台／报告文案含「抽检未人评」
- [x] P010 evidence 谨慎追加；文档；T20 ✅