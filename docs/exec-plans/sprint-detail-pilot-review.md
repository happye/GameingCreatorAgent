# 同候选对照的本地人工记录

2026-10-06，接5bc7029和1683/1skip完整验证。上一Goal turn为实际进展：交付同源对照页、真实双尺寸/下载验证、完整验证与远端核对。按总方案继续Phase 0质量验证准备，不新增模型调用或扩大验收。

## 使用效果与边界

用户可在本地记录页分别填写物品误认、切镜真实性、原正确描述保留、查询片段可用性，下载并重新载入记录。保存入口重验当前来源及每组精确请求/结果/注册帧，拒绝混用其他结果；无真实新版结果时判断、目标实体和说明均保持空值。旧描述意见不扩大为新版或Top-10标签。

日期/填写人可记录；填写任何判断须同时给出日期、填写人和说明，未判断保持null。true/false的含义按问题单独解释，不合成一个模糊通过分数。实体仅引用当前v4 scene的entityId，不借用旧shot/actor ID。输出是新的本地记录包，不覆盖原报告、反馈、画面、侧车或账本。

## 归属与计划

root在codex/visual-details顺序开发；独占新application/detail_pilot_review.py、infrastructure/detail_pilot_review_files.py、tests/test_detail_pilot_review.py，并修改自己已集成的scripts/prepare-detail-pilot-comparison.py及其测试。已有worker及worktrees冻结，不发起并行writer。

1. 纯Application严格解码并绑定原模板来源，保留四个判断维度及空值，支持完整原记录的再次编码。
2. 本地记录页填写／载入／下载；使用显式本地文件，不访问网络，原图与描述可对照，新版缺结果禁填。

归属补充：root同时独占新ui/pilot_review.py和ui/static/pilot-review.js，页面渲染放在UI、文件I/O放在Infrastructure；scripts作为组合入口，不让Infrastructure导入UI。
3. 现有只读生成器增加显式记录页输出与record验证/保存模式；每次重跑原来源核对，不仅信任外来JSON自报hash。输出新目录独占文件，原记录不覆盖。
4. 覆盖换case/request/payload/frame/源hash、bool冒充整数、重复键、非法日期/实体、缺结果打分、空值及跨字段伪造；真实原六帧和1366/390操作回放、源快照不变；最终一次完整verify。

恢复：开始时root工作树5bc7029干净，scaffold检查通过；本切片尚无实现或新验证。先完成纯合同再接记录页，未通过源码仅保存检查点，不替代旧1683。新v4授权待答、0新请求/预留，旧unknown¥4.065536和F006/F009/F010保持。

## 已实现节点：定向与真实资料往返通过

发布核对：普通HTTP/1.1 push成功，随后独立ls-remote确认0b6c10b0a014ccc64079c054ac69e114ffd7905b与本地一致；只更新codex/visual-details，没有main/强推。结论文档后续保存并普通补推，最终核对记录.cache/detail-pilot-review-publication.json。当前完整验证后只改文档。

最终完整verify源码检查点c759450：**1745 passed/1 Windows文件symlink权限skip，186.58s**；Ruff133/mypy71/CLI及两个同SHA离线wheel 65126fc5e6f7dea0867672063d52e9fa2800c08353a4196629d696b4345d8b54通过，日志.cache/detail-pilot-review-verify.log，最终输出摘要.cache/detail-pilot-review-verify-summary.json。完整检查后只改文档；旧1683和下方“待完整检查”是此前节点，不能覆盖本段最终结果。新JS及三个Python模块已在wheel内逐字节核对匹配源码。

root纯合同、独立文件包、UI renderer/static JS及原生成器显式--review-editor/--review-file模式已完成。定向87 passed/11.66s（62新记录行为、22原对照、3架构），Ruff/strict mypy四文件通过；记录界面使用限定hash脚本CSP，无外部连接，所有旧描述和说明按文字展示。错误载入先整体验证，不覆盖原表单；重复JSON字段、来源变化、无新结果打分、错实体、非法日期/类型/说明均拒绝。

真实editor产物artifacts/detail-pilot-review-20261006/review-editor.html；原comparison HTML/JSON/template SHA仍分别4323e6e8b2f1b2f8a5792f613487dade9f6514ffd9f806f0116a63a03ded971f / a41f686bdc158e20e36a1b1973a42ca367f2fde973148941f1779e8309c4250d / ad78d358cc0a855fe639d051144146631aab0d541f49fc498561bdecdf99b666。新editor SHA34f1ed097c5fcf105cb1aca3f82f38dd0dda78ea201894900a7d2d7872fea092。

真实空模板保存到新artifacts/detail-pilot-review-blank-record-20261006，再由同一CLI --review-file/--dry-run读取通过，judgedCaseIds=[]、日期/填写人null，未伪造新人工结论。记录包独占五文件：规范记录、原输入字节、完整同帧comparison快照、只读summary、provenance摘要；原源资料不变。1366/390实际页面核对六图原字节/尺寸、缺结果八select及两说明禁填、下载/载入/再次下载字节一致、非法判断拒绝且原表单不变、summary八项未核对，无页面错误/外部请求/横溢；人工与费用均0变化。证据pilot-review-browser-report.json和对应截图/log。

已向用户说明记录来源绑定、真实空记录已保存/再次读取、新版缺结果所以无新增结论，下一动作保存代码与恢复节点、完整verify及通俗指南/报告，再普通推送工作分支。当前完整基线仍1683；不把87定向当新全量结果。生产工作台代码路径未改，无需重启。
