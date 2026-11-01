# Sprint T19：OCR 离线难例夹具（P009）

**状态（2026-11-01）：已完成（待 SHA）**

## 目标

为画面 OCR 建立**本地、可合成、有字节上限**的难例夹具与回归：覆盖风格化标题、低对比等已知痛点；验证引擎链路能处理这些图并产出合格式结果。

## 非目标

- **不做人评结论**、不宣称准确率通过、不触及 F006
- 不把 OCR 接入检索／排名／验收合同
- 不下载字体／模型；不付费视觉
- 不生成大图／大视频（单图硬上限，测完即删）

## 设计

### 夹具目录

- 目录：`tests/fixtures/ocr-hard-cases/`
- `catalog.json`：难例清单（id、难度标签、期望文案、断言策略）
- 像素图**不入库**：测试时用本机 FFmpeg + `msyh.ttc` 合成 PNG，断言 `st_size ≤ MAX_IMAGE_BYTES`，结束后删除

### 难度标签（诚实）

| tag | 含义 | 回归断言 |
| --- | --- | --- |
| `plain_control` | 高对比黑体／雅黑正文字 | 语言可用时，归一化结果应含期望子串（冒烟，非人评） |
| `low_contrast` | 灰字近底 | **允许**读不出；必须不崩溃、读数结构合法；不得据此宣称准确率 |
| `stylized_title` | 描边／阴影／大字标题风 | 同上：允许 miss；只回归“可跑通 + 诚实标记” |

报告／evidence 一律写明：**准确率未经人评**。

### 模块

- `tests/ocr_hard_case_fixtures.py`：读 catalog、合成图、字节上限、清理
- `tests/test_ocr_hard_cases.py`：catalog 完整性；合成上限；Windows OCR 冒烟（跳过条件同既有 ocr 真工具测）

### Acceptance

- [x] sprint 设计先于实现
- [x] catalog + 合成夹具 + 回归测试
- [x] P009 evidence 追加夹具事实，**不**写人评／F006／准确率达标
- [x] 文档；T19 ✅