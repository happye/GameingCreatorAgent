# 同片段旧版／新版对照页

这份本地资料把同一组三张原画面、旧模型描述、已有人工纠错和新版已保存结果放在一起，帮助核对物品误认和镜头连续性；它不会执行模型分析。

## 直接查看

在准备好的工作站打开 `artifacts/detail-pilot-comparison-20261006-final/comparison.html`。页面自带原六张图片，无需工作台服务或网络。35–36秒保留三个已确认描述；28–29秒保留“靠近镜头的物品被认成人物”的原纠错。尚未评判的条目仍未判定，旧确认不自动贴到新版。

新版没有精确请求的已发布结果时显示“未执行／暂无结果”。这时不能判断新版识别是否改善，模板中的新版结论也应留空。旧版两个复合查询仍仅部分符合，三个描述正确不能推出整组属性或查询通过。

“下载人工记录模板”保存JSON文件，分别记录物品误认、切镜真实性、正例描述保留、查询片段可用性。未核对的项目保持空值。模板携带候选、两版请求与结果、原帧及来源身份；当前尚无自动导入、提交或验收功能。“下载对照数据”保存完整来源资料，其中包含原画面。

## 重新生成

先加载隔离环境，用原冻结资料生成到不存在的新目录。以下示例针对这台工作站；克隆仓库不会带来视频、数据库或报告。

```powershell
. ./scripts/env.ps1
./.venv/Scripts/python.exe -B ./scripts/prepare-detail-pilot-comparison.py `
  --project 'G:/Tools/ChatGPTRepo/GameingCreatorAgent/artifacts/demo-phase0' `
  --proposal 'G:/Tools/ChatGPTRepo/GameingCreatorAgent/artifacts/detail-temporal-validation/pilot-proposal.json' `
  --proposal-sha256 06829ab9dc835545ef8c4de5c829351fc686ce70c990d8c902b9b919b2f062c6 `
  --legacy-report 'G:/Tools/ChatGPTRepo/GameingCreatorAgent/artifacts/detail-query-validation/pilot-report.json' `
  --feedback 'G:/Tools/ChatGPTRepo/GameingCreatorAgent/artifacts/detail-query-validation/human-feedback.json' `
  --output-dir 'G:/Tools/ChatGPTRepo/GameingCreatorAgent/artifacts/detail-pilot-comparison-next'
```

用 `--dry-run` 替换 `--output-dir ...` 只核对来源，不输出文件；两者必须二选一。生成前核对proposal摘要、候选run/event/request、旧报告与当前结果、原帧源时刻/hash/尺寸，不一致就拒绝。输出目录必须为绝对路径、不存在且不包含源资料；不覆盖原人工记录，不清理或重用先前目录。

成功输出 `comparison.html`、`comparison.json` 和 `human-review-template.json`。文字安全显示，图片和JSON下载内嵌页面，无脚本或外部连接。只读取精确版本结果，不扫描“最新文件”代替指定结果。

## 验证边界

真实1366/390页面核对了六图原字节与尺寸、三个确认和一个判错、旧反馈隔离、模板实际下载及无横向溢出。源数据库、侧车、账本、原反馈和冻结资料保持原值，模型调用和预算变化均为零。

两组描述不替代Phase 0检索验收：每个主要查询十个固定位置，缺位和重复事件计零，至少七个独立有用事件。程序检查与结果复用不能证明动作理解或检索质量。见[执行记录](../exec-plans/sprint-detail-pilot-comparison.md)与[人工验收指南](./human-acceptance-guide.md)。
