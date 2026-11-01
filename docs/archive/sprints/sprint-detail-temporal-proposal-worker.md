# v4 正反对照的只读审核清单

2026-10-06，owner `detail_parts_v3`，独占 `.worktrees/detail-v4-proposal` / `codex/detail-v4-proposal`，基线 `4a84c40`。只新增准备脚本、18项测试和本文；旧temporal实体worktree冻结，不回写root或其他agent。

## 使用效果与已汇报结论

已经准备好可审核的两组新版本对照：35–36秒三个角色描述的保留正例，以及28–29秒物品正抵镜头并遮挡人物的失败反例。每组仍只用原候选的三张注册图，合计原六图；没有偷加29.5秒切镜上下文，也没有从别的run借画面。清单保留完整新提示词、请求参数和每张图的时刻、尺寸、字节数与hash，可以在发送前明确审查输入与费用。

这一步把“准备实验”与“实际花费”分开。旧v2结果、人评和账本保持原样；清单明确旧两次调用许可已经用完，新v4预算、请求次数及目的地授权仍待取得。程序没有发送请求，也没有落预算锁、预留或结算。

已向root详细汇报上述效果、实际只读证据、费用区别、尚未验证的内容及下一步；公共HANDOFF由root汇总。

## 请求与费用

目标明确写为 `https://api.deepseek.com/chat/completions`，provider/model为DeepSeek/deepseek-flash，独立actor-detail-refinement-v4、请求schema-v2，输出最多4096tokens。每候选最多1次，合计最多2次，无自动retry。actual v4 request hashes：

- 35–36秒：`e733a6cbdd16a9ac55078cc166e44ab0ee29208c51e45c186f2d45b9996fb92a`。
- 28–29秒：`afdc93312f04803bdf9a97d9e23f5514336fbdfd0ef872386e5cb2f36a70b8e6`。

价格仅依据已冻结 `deepseek-flash-cny-2026-10-04` 快照，不宣称当前账单价格。按最高period、不计缓存优惠、每次最多1M输入+4096输出，保守预留每次 **¥2.032768**，两次新增合计 **¥4.065536**。这不是账单或已获费用授权。

本demo项目已有精分析估价 **¥0.01850612**，因此包含项目旧commitment与本次新预留的最小共享精分析ceiling为 **¥4.08404212**；它不是新增预算数字。旧任务的基础vision未知预留 **¥4.065536**另列并保留，不属于该项目精分析账本，不抵扣或清零；后续总任务账目仍须保留它。清单不把旧“追加¥4.04/两次”许可移给v4。

## 实现与验证

`scripts/prepare-detail-temporal-pilot.py` 通过只读SQLite严格 `load_completed_timeline` 加载，重新计算旧v2 canonical请求并与原pilot-proposal的候选/hash逐项相等；再准备v4同原帧请求。仅执行Provider的输入payload构造与图字节/hash/尺寸/范围校验，transport硬拒绝发送，不调用refine/post。保存新canonicalRequest、prompt/base身份、图与线序文本、参数及规范payload hash。

CLI先以 `--dry-run` 只读打印摘要；正式输出必须显式绝对 `--output`，以exclusive-create写入，拒绝覆盖既有文件或写到源项目内部。源SQLite和全部现有侧车/预算文件在读取前后逐文件hash相等，旧proposal SHA也相等。输出在ignored artifacts，未提交图、媒体、数据库、结果或凭据。

18项必要测试 **18 passed / 0.74s**；脚本与测试Ruff/格式通过，脚本strict mypy通过，scaffold CheckOnly11项通过。覆盖改图/缺图、候选事实变化与跨候选、额外原范围外帧、未Completedrun、旧attempt缺失、sourceDB缺失、真实Completed loader拒绝缺失/变化源视频、并发DB/侧车/ledger改动、无HTTP/预算行为、费用未知不释放与exclusive输出。

实际CLI先dry-run再冻结一次，paidRequestsSent始终0，new request hashes相同；源DB/全部侧车/ledger前后未变。冻结文件：
`G:/Tools/ChatGPTRepo/GameingCreatorAgent/artifacts/detail-temporal-validation/pilot-proposal.json`，SHA256 **06829ab9dc835545ef8c4de5c829351fc686ce70c990d8c902b9b919b2f062c6**。包含pre/post证明；`realV4RecognitionVerified=false`，humanLabels/qualityGate=null，不以清单或fixtures证明真实识别修好。第一组用户只确认三个描述，不扩大到全部属性或Phase0质量验收。

## 下一步与恢复

root审查并整合准备脚本，向用户展示这两个新冻结候选、指定发送内容与目的地、追加预算和最多两次无retry规则。取得新实验许可后才能实施受控真实对照；本任务没有执行入口、旧run retry或任何预算变更。源码提交后本worktree冻结。

复现只读检查：根env.ps1、项目Python `-B`、PYTHONPATH指向ownsrc，然后脚本 `--project <绝对demo-phase0> --baseline-proposal <绝对旧pilot-proposal> --dry-run`。不要再次覆盖当前冻结JSON，需修改方案时另选新review文件并重新审核。
