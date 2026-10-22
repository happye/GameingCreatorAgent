# 长钟馗接手记录：P1与接续已完成

2026-10-22恢复提示：先读[当前里程碑及素材需求](current-status.md)与[HANDOFF](../../HANDOFF.md)。下方旧接手顺序／待批准／运行中段落是历史，不重做修复、标注或付费执行。

**最终接手入口（2026-10-12）：本轮已完成，实际guard PASS。** 首先读HANDOFF及execution-outcome-v1／evaluation-execution-v1，不重启任何launcher、不重做修复／测试／抽帧／标注。269成功／3拒绝／0未执行、469观察，250新调用各一次，新¥1.38173400／总¥1.49022124／0unknown；旧媒体／进度／费用／参考保持，进程已结束。当前无人工动作、无自动补发权限；完整分析及正式质量验收仍需独立缺口处理路径，F006/F009/F010false。下面实际核对中与启动前都为历史。

**实际接续已结束（2026-10-12）**：已获“刚才断了，继续工作”的v2接续指令并唯一执行完250新窗口；842.598秒，269成功／3拒绝／0未执行，469观察／0转录。新¥1.38173400／总¥1.49022124、总272请求／2445帧次／maxAttempt1、0unknown；旧21成功／22调用、3160文件及标注保持。新两拒绝隔离后继续到尾，实际P1有效；保留3缺口使failed/analysis.coverage_gap，非Completed／不绑定评分。execution-started/process/finished/outcome齐全，79777/PID41752已结束，不再运行launcher；恢复直接读HANDOFF与真实终态，不重复开发／费用任务／抽帧或重标。当前唯一guard实际边界核对中，之后仅最终文档本地保存；完整资格需另行缺口方案，旧授权不自动扩展。下面为启动前历史。

**最新接手顺序（2026-10-12修复后）**：P1调度修复完成，295相关／32新边界、格式lint/types及唯一guard差异复核PASS。读HANDOFF与sprint当前顶部，不重复开发／完整测试／抽帧／导入／标注。v2方案在artifacts/long-analysis-reliability-20261011，SHA aa2299e81325a905a2d032a6bb99288710aa05c2422c2fbc49f673979ed1c9d0；沿原run只分析250未执行，旧21成功和第22拒绝不重发，原总¥5剩余最大¥4.89151276。新方案费用／图片发送尚待具体批准；获准后另存authorization绑定v2与evaluation-final-v2 SHA，只运行新execute-continuation.py一次。无后台分析／0新请求，原费用和3160文件保护不变。第22缺口保留，预期非Completed，不能绑定评分。下面为修复前交接历史。

2026-10-11交接。用户准备在同一工作区开启新对话；本轮只整理交接，不新增付费请求或产品代码。新对话已有仓库内开发授权，读取后直接推进离线修复，不先问“是否继续开发”。

## 停止原因与优先级

第22窗口第三条事件把开始和结束选成同一源帧（77.533500秒），映射区间77533500–77533501us。V6提示词要求不同起止帧，多帧动作解析拒绝是正确的。

错误传播已确认：infrastructure/deepseek_vision.py:649拒绝事件，将该窗口返回provider.schema；application/analysis.py:665–669将窗口失败抛为AppError，:725触发_abort，把整个任务置failed，CLI退出4。结构错误不可自动重试，所以停止后没有继续发送。不是预算用尽，也不是用户要求停止，是程序当前流程的自动行为。

**TD007列为P1：阻断长录像主要交付的可靠性缺陷，下一开发优先项。** 拒绝不合格事件合理，单条异常导致整片中断需优先修复，不按普通小bug延期。修复不能放松不同源时刻／多帧证据要求、吞掉失败或伪造Completed。四项边界检查通过只证明保护生效，不证明稳定性缺陷已修复。

## 必须保留的现状

| 项目 | 已核对事实 |
| --- | --- |
| 工作区／分支 | G:/Tools/ChatGPTRepo/GameingCreatorAgent，codex/visual-details；最新HEAD由git读取 |
| 原片 | GameVideos/黑神话：钟馗/1.《黑神话：钟馗》15分钟实机演示(Av117123103856658,P1).mp4，952.101688秒 |
| 来源SHA | 7437abfab778b0f0b6d67efec5f8f80a61e28f9d5bd4ba681908c5f44b9890ac |
| 项目／任务 | artifacts/independent-footage-20261011，run5c7894aa10e94b8aa82533bd77f9871e |
| 媒体 | 1903注册图及原音轨已经准备，禁止重抽／改图／改源时钟 |
| 终态 | failed/provider.schema，21／272窗口完成，1失败、250未执行；19观察、0转录 |
| 调用／费用 | 22次／198帧次，全attempt1，估算¥0.10848724含失败¥0.00612692；0新unknown／未结预留 |
| 保存参数 | ¥5、500实际请求、5000帧次，phase0-vision-v6及原模型／pipeline／config身份，不能硬改数据库 |
| 另两任务 | f031d88e7c84457bb985f7cb5c998013、5f5ccf9cea3f4a3bb42bee058df7213c，pending／0调用 |
| 真人参考 | 原根目录JSON不改；12事件按用户确认排除两特写、纠正老者理由，10样例为boss1／连招5／剧情4 |
| 需求／未知项 | 武器只找装备菜单等界面，特写不算；未填和“似乎没有”不当负例，未确认全片标签穷尽 |
| 阶段 | Phase 0，F006/F009/F010false；partial不能绑定Completed／正式评分，全片Recall未知 |

## 新会话第一步就做什么

1. 读AGENTS.md、HANDOFF.md、本文件和sprint-long-analysis-reliability.md，核对git／环境／归属；复用项目.tools、.venv、.cache，init -CheckOnly不重新初始化或改全局环境。
2. 定点读execution-outcome-v1.json的摘要／failedAttempts与evaluation-execution-final.json，不递归.cache或倾倒重复材料。第22原始响应未保存，不能假设其中其他事件有效。
3. 直接完成P1合同并实现版本化窗口失败策略：隔离局部不合格返回、保留拒绝证据和费用，在策略允许时处理后续窗口，最终明确覆盖缺口与资格。预算／认证／存储或身份错误仍停止。不要只改提示词再付费试错。
4. 入口为application/analysis.py、infrastructure/deepseek_vision.py、application/inputs.py、application/storage.py、infrastructure/sqlite_store.py。主控持公共记录，实现owner在assignments明确；按既定三角色流程使用唯一关键边界评估，不叠加普通reviewer，并行写者分worktree。
5. 离线验证“前窗口成功→当前结构错误→后窗口可处理”，及预算／unknown、恢复不重发成功窗口、缺口不得伪装Completed、并发锁及来源／费用身份。只跑相关检查，完成实际实现后再准备具体续分析提案。
6. **继续验证同一长钟馗原片**，复用媒体、保留21成功窗口／原run／全部费用与参考。若保存配置不支持新策略，显式设计关联延续版本，不悄悄改原配置或抹掉历史。具体发送与费用提案冻结获准后执行，满足Completed才绑定、生成三类固定结果并提醒真人评分。

## 权限、人工和恢复

旧v2 SHA f608c4dedac69ee261ac56ba110c8446e808bfc533ed26116b568c95fe8c6f6f的答复“允许按此方案执行并发送图片”已执行并按失败停止。提案不改、授权另存；未用完¥5不是手工重跑或换策略许可。不重提旧批准；新付费续跑先有具体新提案，本地离线开发不需重复批准。

当前不用用户补标、重填验收、确认账单或评分。现有10样例足够有限对照；用于调优后正式验收另换独立材料。旧v5稍后核对和所有旧unknown依human-inputs保存，不重复催促、不清空账本。

证据在artifacts/human-reference-pilot-20261011：authorization-granted-v1、execution-preflight-v1、execution-started/process/finished、execution-outcome-v1、evaluation-execution-final、delivery-execution-report、analysis-stdout/stderr.log、boundary-check-after.xml。步骤已完成，尤其禁止再运行execute-authorized-analysis.py或exclusive输出助手。

执行句柄91845已结束，PID35160仅历史；没有后台分析要等，不据旧PID操作进程。准备批次已完成。references-v2、imported-v1、frozen-v1不改，冻结SHA8cc6fffcc8693d93ca850a9d35a188b01ef5d7f38d6822cc5f73eeea5a8556b4保持。

Git尚待普通补推：最后确认远端f5a3a69898747917d6477d6985efc2593bb14421；用户断网后仅本地保存，旧许可只限codex/visual-details，不动main／强推。实际HEAD以git及.cache/independent-footage-publication.json为准。旧交接归档handoff-history-2026-10-11-long-analysis.md，不从历史“暂停／未授权／待标注”重启工作。
