# 三段新素材的本地验收准备

最新人工反馈：用户正在标注，要求说明每框如何填写及原因，再次询问结果。root已按真实表单核对并补充docs/references/benchmark-reference-fields-guide.md，明确版本／填写人／两声明适用整份记录，片段时间用总秒数，同次动作不重复计数，先登记后下载。假设连招示例不作真实标签；当前references-v2包不改写，待收最新记录路径、完成范围及缺例后核对，不重复媒体或测试。

2026-10-11，Phase 0／F002／F006。**本地准备与原片参考入口已交付，真人区间待办。** 用户提供《黑神话：钟馗》两段和CIG《42中队》一段，事前指定boss战、武器展示界面、释放连招、剧情演示，明确“都没看过对应的AI结果”；原等待素材位置／查询条件已解除。真实录制分组和正确事件仍待真人，不能据文件名填写独立标签。F006/F009/F010保持false。

root单Agent复用既有登记／批次准备／参考入口，拥有本sprint、菜单文字、人工待办和公共进度；无需新后端合同或重复评估者。新增资料在artifacts/independent-footage-validation-20261011，待分析任务在独立artifacts/independent-footage-20261011，旧demo与原验收流程保留。

交付顺序：核对三原文件／实际时长／SHA及隔离环境；生成只含实际路径的可继续登记草稿，未知声明和查询留空；按既有v6采样配置在本机抽帧／提音轨，保存pending任务。准备仅保存以后分析的每任务上限，不是费用授权，0模型请求／预留。用另一进程读取三任务及媒体阶段／调用计数，核对原素材和旧项目保持。随后给出实际播放／登记入口，提醒真人确认具体查询与原片参考；正式分析须另行冻结并授权，不在本轮自动启动。

验证范围是三素材本地准备和持久化，不等于模型理解、独立来源或70%质量通过；F006/F009/F010false。已有TD012／TD014不循环追修，不重新跑未变源码的完整套件。出现单项媒体失败保留回执，按批次合同继续可处理项；身份／存储异常停止相应写入。

root额外拥有ui/static/benchmark-references.js的一处菜单文字变化：同一查询用于三录像时显示原录像文件名，选项value／查询与source绑定保持。这是直接影响真人选对原片的简单修正，单Agent；复用既有原片浏览器／合同检查及实际12选项证据，不追加重复审查或完整套件。初辅助浏览器检查误按queryId选择，原控件value实际是索引；按现有脚本改为真实索引核对，不改产品身份或重试业务步骤。v1页面未提供用户填写，保留历史，当前交付用新references-v2包。

## 实际交付和恢复身份

| 素材 | 实际时长／准备图数 | 保存任务 |
| --- | --- | --- |
| 《钟馗》15分钟实机演示 | 952101688微秒／1903图 | 5c7894aa10e94b8aa82533bd77f9871e |
| 《钟馗》6分钟实机小短片 | 406762667微秒／814图 | f031d88e7c84457bb985f7cb5c998013 |
| 《42中队》预告片「宣誓」 | 213717334微秒／428图，AV1 | 5f5ccf9cea3f4a3bb42bee058df7213c |

三文件共26分12.58秒／3145图／三音轨，批次ce93cda042794fd4b2916a8e0cf8b2a7在48.449秒完成、exit0。仅media_prepared／pending，视觉事件及转写均0，模型调用／新预留0。既有config.detailed-v6.example.json按0.5秒取图，九图窗口、重叠二；configHash 598a28d261a2d2386ab0218ae773755b2eda28de7b07a6097ad58ced49f6b235。以后完整分析计划449窗口／4037上传图，当前没有上传。保存每任务MaxCostCny=5仅是原准备参数，不是授权、实际费用估计或新预留；旧两个v5试验许可不能复用。

原源路径与完整SHA在baseline.json、batch-result.json及各probe记录；三原源／demo既有923文件在完整读回后逐字节保持。批次handle21068、独立读回handle37452均已结束，不得因恢复重新抽帧。task-list.json及逐任务CLI输出是metadata快照，integrityCheck=not_requested；实际完整性依据另一进程的load_run／load_media_bundle与delivery-report.json。检查helpers的报告采用exclusive输出，不重复执行。

用户原答在source-input.json和pre-reference-provenance.json保存。四查询族×三source=12组合；modelResultsViewed=false来自明确原答。两钟馗保守同组zhongkui-conservative-combined，另组squadron42-trailer，录制真实关系未确认。query.kind暂main／referenceEvents=[]／labelVersion=null／annotators=[]／confirmed=false／reviewed=false，不从片名猜boss或武器内容。若原片对应内容不足，应如实定为少例／负例或补素材，正式冻结前处理；来源／查询种类变化须新准备并披露，不直接改已有参考包。三文件／两个保守组不证明完整代表集或独立会话已验收。

当前仅交付references-v2/review.html，整目录保留。receipt记录plan-input SHA e8328fea44f1dd458b421b89acd40ade044ac6ff01236088b71655c457860063、context SHA 4eb42ab580f65dd025d382fe483e1c6a87cee8e7937f2c660287dd6ce5bb636b、template SHA 676b052bae61e81722543882b15fe07d02c980d6dd047ba6500202c67f94ec2c。references-v1为菜单修正前的未交付包，不覆盖它或用户已有标注。

## 已完成的验证

隔离init的CheckOnly与媒体前置检查通过。独立媒体读取核对全部注册图与原源；实际工作台1366／390发现三新任务，三原录像均能seek至2秒播放／暂停，AV1也可播放，无横向溢出、外网或HTTP变更。参考页两尺寸12菜单项均为准确且不同的“查询·原录像名”，索引0／4／8切换实际来源，三视频播放、空记录下载与原未确认模板完全一致。delivery-report.json及reference-page-report.json分别保存证据。

既有tests/test_benchmark_reference_browser.py及tests/test_benchmark_reference_review.py共22passed，JUnit在.cache/independent-footage-reference-tests.xml；不是22个新增测试。源码只改一个菜单文字，不重复完整verify或双wheel；此前费用包检验属于历史检查点，不声称当前JS仍等于旧wheel。真实humanLabels与qualityGate均null，准备不等于模型理解或70%通过。

## 已向用户汇报／人工待办／下一步

已解释三素材本地可读回／播放、需求登记、菜单来源与零模型费用；给出当前原片页并说明：看原片、标正确起止、登记真实事件与理由，关闭前下载保存，可分批继续，同一动作不多算。已即时询问保存记录的本地位置及确实缺少内容的查询；没有代填参考、确认人、版本或评分。待办同步human-inputs.md；旧28–29秒仍按“稍后核对”保留。

拿到真人原片记录后核对原包／SHA与参考、录制分组和查询分类，再按原F006冻结流程推进。新分析先有具体冻结费用及发送提案、取得新授权；之后明确Completed绑定、固定十位检索／真人判分，不在事前标注前展示模型结果。缺位与重复零分，主查询至少十个独立参考、固定十位至少七个不同事件有用；完整代表集及时间／费用指标继续核对。用户再次说断网，本节点0Git网络动作，源码及文档本地提交，授权codex/visual-details待恢复补推。下一步不是重复旧费用导入、媒体准备或微修TD012／TD014。
