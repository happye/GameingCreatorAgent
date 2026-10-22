# 已有细节联合检索记录：DSH协作交付

2026-10-22，Phase 0限定里程碑完成。用户保存的含已有细节联合排名可继续读取；v1/v2/v3和普通排名保持兼容，串错版本、来源或损坏细节元数据会明确拒绝。接手时已有153行未提交草稿，先保存快照再完成，没有重新开发已存在的检索功能或更改排名算法。

## 实现与用户效果

`assert_project_search_document_contract`把细节版本和检索版本配对，核对支持的profile、完整来源身份、计数、精进属性、语义组与规范摘要。错误沿用`retrieval.detail_snapshot`。实际构造器→CLI保存→读取覆盖v1/v2/v3及无细节记录，损坏用例验证具体拒绝路径。恢复旧排名无需重做标注或模型分析。

原生DSH仅写`src/gamingcreator/application/retrieval.py`、`tests/test_project_retrieval.py`、`tests/test_saved_detail_retrieval.py`。另对同文件直接静态错误整理导入、复用已验证候选列表、分开embedding结果变量名及格式；独立AST审查确认排名函数变量归一后与原快照相同，其余既有函数仅格式变化。

## 原生工作区与实际协作

- 真实目录：`G:/Tools/ChatGPTRepo/GameingCreatorAgent`，与Codex项目相同。
- 独立原生workspace：`f4395711-a8fb-49a3-ad95-7305ce9ea1e8`，成员关系已从原生控制器读回。
- 新对话：`codex-a18e5d7c-0550-4920-a860-ea1da4d61a2c`，标题`GamingCreator Phase 0 · DSH 协作开发`。
- task：`gamingcreator-workspace-phase0-20261022`；connection `native`；账本目录`C:/Users/Crux/.codex/codex-dsh-state`。
- 两次逻辑开发派发：`ca0044d3-26f0-409f-ab08-64950d78b345`、`ce92c9d0-4432-4f44-bd0a-923806783cd1`，均COMPLETED；完整答复已逐份读取并核真实diff。未因超时重复投递。
- 先前未指定workspace的空task `gamingcreator-phase0-20261022`未发prompt、0请求，已STOPPED；勿复用。
- Codex负责规划合同、实际回归、文档与Git；Luna/high只读定位；唯一Sol/high独立评估。实际执行metadata另存`explorer-runtime.json`、`guard-runtime.json`，非依据Agent自报型号。无递归委派或第二reviewer。

## 实际验证与失败保留

主控按rev4合同`aadcc33a16a56d1a6b32db23a6639adceaa9d3ad92de8abb79230f23fa772021`执行并重读三组回执，均`valid/evidenceComplete/passed=true`，退出0，执行前后sourceFingerprint均`684602b7a84e8a6e00b08036552575d8f161033a2f9565fee7a0626428952936`。

| 检查 | 结果 | run ID |
| --- | --- | --- |
| project_retrieval／saved_detail_retrieval／saved_detail_grouped_ranking | 98 passed；JUnit失败／错误／跳过均0 | `769424aa-4ee4-4529-9cf2-63a15ad10364` |
| Ruff三个owner文件 | All checks passed | `a35d2fbf-b039-4a2d-9cbd-fc43a06ba778` |
| mypy retrieval.py | no issues found | `801de800-2860-4b76-ac4b-973155eae6de` |

计划runner为command；pytest结论依据真实stdout及JUnit，不声称工具原生pytest收集器证明。未执行整仓verify／wheel／真人质量验收，未把程序检查称为动作理解准确。

首轮实际结果81 passed／17 failed：新复制夹具及一个既有夹具只换searchId、未换recordPath，被正确旧守卫提前拒绝。DSH同步身份和路径，并明确版本用例v3→v2，未放宽正式校验。首轮Ruff I001及4个直接类型错误亦已修复。失败原日志／JUnit保留，修正后才按明确理由复测。合同rev3仅暂分离大型runtimeInputs清单以避免重送模型上下文，要求未删改；rev4恢复完全相同三组测试计划及完整依赖清单。

唯一独立评估最终PASS：读完整答复、真实diff、原草稿和构造器；32份本机真实排名均可读（普通16／v1 10／v2 5／v3 1），result及receipt SHA与实施前一致；源码增量及实际回归证据均无待修阻断。

## 环境与证据位置

完整init通过。143个登记stdlib pyc从固定SHA本地原归档恢复，receipt未改。测试首次启动前被协作工具的硬链接检查拒绝，确认无execution intent／run，未启动pytest；4652个uv硬链接依赖在项目`.venv`内转为逐文件SHA相同的独立副本，未更改全局环境或cache内容，然后才启动实际测试。

忽略目录`artifacts/dsh-phase0-20261022/`保存合同v1至v4、完整派发文本、原草稿、前后验证源码身份、初次失败、最终三组原始stdout/stderr/receipt、JUnit、32份原记录摘要及运行型号、环境修复记录。`validated-source.json`在文档／Git变化前保存文件SHA和Git blob，将本次测试关联到具体源码内容。公共文档／Git变化后旧合同基线不再作为当前可复用回执；不篡改账本或旧基线绕过工具门禁。后续新里程碑须按支持流程建立当前Git基线。

原生usage可见81条调用用量记录，包含两个逻辑派发；未缓存输入385304、缓存读取31941120、输出92781 tokens，详见`dsh-usage.json`。这仅是该原生会话可见用量，不等同提供方请求总数或实际账单；没有价格或费用硬上限结论，更不声称本轮协作免费。开发模型费用与原录像分析账本分开。

## 保留与下一步

本轮无录像分析／发图／嵌入下载／数据库／人工标注写入。长钟馗P1修复与到842.598秒片尾的接续已在此前完成；269成功／3拒绝，0未执行，原run估算¥1.49022124、0unknown／预留等终态沿既有报告保存。本轮不重跑launcher，不补缺口，不把旧余额当授权。

F006/F009/F010仍false，普通SHA摘要只证明自洽、不提供恶意重签防护。下一仍按既有独立质量路径保留已填原片参考、明确Completed版本选择、冻结绑定及固定Top10真人判断；不要求重新标注。三缺口及A/B/D仍沿原human-inputs记录，无新必答人工项；任何新增付费分析／定向补窗仍须具体新提案与授权。本轮元数据兼容交付不替代人评，不宣称TD009或F006通过。
