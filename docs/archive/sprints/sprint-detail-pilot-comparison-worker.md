# 同源 v2/v4 对照审核页 Worker

Owner：Codex worker `/root/detail_parts_v3`。独立分支 `codex/detail-pilot-compare`，基线 `a424ef4`，仅修改本 sprint、`scripts/prepare-detail-pilot-comparison.py`、`tests/test_detail_pilot_comparison.py`。其他工作树冻结；root 负责实际产物生成、桌面/手机浏览器核对和共享交接。没有新增调用授权，不执行 HTTP、Provider、预算锁、预留、结算或旧任务恢复。

## 能做什么与使用帮助

将用户反馈过的两个冻结候选放在一份本地对照页中：35–36 秒三个角色描述的保留正例，以及 28–29 秒物品抵近镜头、遮挡角色的失败反例。每组原来的三张注册画面原字节内嵌，只展示一次；左右显示旧 v2 描述/已有明确反馈/同一查询结果，以及 v4 精确保存结果。v4 尚无此精确请求的已发布结果时明确显示“未执行/暂无结果”，没有替代候选或虚构结果。

旧反馈只贴旧 request/payload 的 shot/actor，其他描述保持未判定。新版的角色/物品判断、可见与遮挡、持有关系和画面边界来自通过现有侧车校验的完整 scene，不把物品升级成角色，也不移植旧 actorId 或旧结论。原 query-v1 查询保持相同，旧版原报告的程序结果逐项与当前同版 matcher 相等；描述正确与组合检索部分符合可以同时成立。

独立人工记录模板把“物品是否被误当角色”“切镜是否真实”“正确描述是否保留”“所查片段是否可用”分开，默认全部 null，并绑定旧/新请求与载荷、原帧 ID/源时刻/hash。未填写不推断，不能作为 U10 或 Phase 0 质量门槛通过。模板可下载，当前不实现反馈提交/自动导入流程。

## 接口与读取边界

```powershell
python -B scripts/prepare-detail-pilot-comparison.py `
  --project ABS --proposal ABS --proposal-sha256 EXPECTED_SHA256 `
  --legacy-report ABS --feedback ABS --dry-run
# 或将 --dry-run 替换为 --output-dir ABS（必须是尚未存在的新目录）
```

输出固定为 `comparison.html`、`comparison.json`、`human-review-template.json`。绝对新目录不可位于 source project 内，不可包含输入文件；已有目录不覆盖。root 的独立 ignored `artifacts/detail-pilot-comparison` 存放生成产物，不提交图片、媒体、数据库或产物。

要求调用者提供冻结 proposal 的预期 SHA；复核两 case 唯一性、项目/run/event、当前 v4 canonical request/hash、候选指纹、原三帧 ID/源时刻/hash/实际 JPEG 字节/尺寸/范围。旧报告使用现有严格 DescriptionFeedback DTO 与 validate_description_report，并与当前 v2 精确侧车载荷相等。新结果仅通过 v4 身份/settings 的 reuse_or_refuse 读取；损坏或错身份拒绝，不恢复、不预留、不发送。

读取前后检查 source SQLite/WAL/SHM、全部侧车和预算文件 SHA，以及 proposal/report/feedback/原图 SHA。HTML 所有文本转义，原图 data URI；无脚本、外部资源、表单或发送按钮，CSP 禁止 connect/script/object/base。root 会独立核对浏览器与下载行为。

## 2026-10-06 检查点

初版 16 个定向测试通过，脚本 strict mypy 通过，Ruff 初次检查通过。真实 source `artifacts/demo-phase0` 的只读 dry-run 已通过，两 case 都为 `no_saved_result`，paidRequestsSent=0，数据库/侧车/账本与输入文本 SHA 不变。冻结新 proposal SHA 为 `06829ab9dc835545ef8c4de5c829351fc686ce70c990d8c902b9b919b2f062c6`。

实现期间测试 fixture 初次错误使用空 partGroup、再使用默认非 v2 身份，已改为合法 hair 分组及明确 v2 身份；属于测试数据错误，未改变现有 domain 或 Provider。root 初审指出仅比较旧 match 身份可能渲染伪造的程序结果，已增加完整 result 一致性和 report/case/match 的 null 人工质量字段检查，并加入重绑报告 SHA 的反例。补充原图读取后的再次 hash 核验和中文查询状态，避免把部分符合描述成全部通过。最后一轮渲染测试发现新生成的 match report 保留 StrEnum，显示层应接受其字符串值；已修正，未放松输入 JSON 的严格类型检查。

最终证据：21 个定向测试通过（包括已保存 v4 正例/缺结果/身份与帧篡改/坏侧车/重绑报告 SHA 伪结果或人评/HTML 转义/输出不覆盖/零发送）；两 owned Python 文件 Ruff format/check 通过，脚本 strict mypy 通过。补丁后的真实只读 CLI dry-run 再次通过，两 case 均 no_saved_result，发送 0 次，数据库/全部侧车/账本及 proposal/report/feedback/原图 SHA 前后不变。未扩大为全量 verify，集成与实际页面核对由 root 完成。

已汇报给 root：当前两例暂无 v4 真实模型结果，只读对照能力已实现，不能称识别改好。既有三个描述确认和一个误认错误仍只属于旧版。未进行真实模型调用、费用动作、U10 人工评判或新质量验收。

下一步：交付上述三个 owned 文件的可恢复提交并冻结接口；root 集成后实际生成新 HTML/JSON/人工模板，检查桌面/手机页面、六图原字节与真实模板下载。真实识别验证仍需独立新调用授权及后续人工对照，当前任务不抢跑。用户恢复 Codex 额度不等于新的 DeepSeek 预算或图片发送授权。
