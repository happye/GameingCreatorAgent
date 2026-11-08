# Studio 知识与本机旁白修订收口

日期：2026-11-08。接收 Grok 第二轮已有成果并收口；P018/P020仍为部分实现，不代表创作质量、人评或分发验收。

## 合同与边界

已有本机知识进入动态策划准备、实际请求与引用；用户修改挂接旁白后，可免费本机重合成并保存新修订。失败、越界或等待期间编辑状态变化时保留当前音轨；新旧修订分别可回读，旧证据不改。复用既有任务、费用确认、修订、FFmpeg与发布包路径，无新数据库、真实云端发送、付费语音或平台投稿。

唯一task_quality_guard（Sol/high）审查知识费用/快照/来源、audio、knowledge.js及narration_drafts.js边界。发现并修复两项P2，均由同一审查者定向复核通过：

- 重合成期间撤销参数或裁剪，迟到结果会按旧参数/旧时长覆盖。现按clips/audio编辑代次隔离返回，包含ABA。
- 新音轨B编辑期间撤销回A，B稿可写入A草稿键。现资产ID变化关闭编辑会话、清空旧状态并使异步结果失效；重新打开按当前资产键恢复。

## 定向与真实链路证据

1. `tests/test_studio_narration_revision_browser.py`：4 passed /20.79s，Ruff/format通过。覆盖失败保持、成功保存新修订后新旧asset/start30/gain-6/mix回读、延迟撤销隔离、A→B→撤销A后恢复A原稿。日志`.cache/studio-resume-revision-scope.log`，XML同名。
2. 独立媒体链：`.cache/scratch/resume-real-media.py`与`.cache/studio-resume-real-media2.log`。两条真实2秒WAV（明确fake本机引擎，440/880Hz）经真实旁白任务/两版修订，真实FFmpeg输出180帧/30fps/6秒MP4，再生成B站七文件ZIP。旧修订所有原文件字节保持。索引`.cache/scratch/resume-real-media/result.json`。
3. 同库任务链：`.cache/scratch/resume-full-journey.py`，日志`.cache/studio-resume-full-journey-final.log`退出0。真实规则HTTP提取主题→普通计划Brief→真实知识HTTP登记→动态prepare，确认前发送0次；明确fake文本输出合法v2，实际user逐字等于报价预览，确认/采用/重复采用后发送共1次，采用结果重读含该entryId。随后同库两版旁白任务/修订→真实MP4→publication→B站ZIP。索引`.cache/scratch/resume-full-journey/summary.json`及planning-evidence/result。6秒旁白预算18字未容纳知识句，此短样例不作为引用展示证据。
4. 同库Studio引用与草稿：`.cache/scratch/resume-ui-journey.py`（SHA256 a478b3f07d93bd219b54eb7cfb28880e87c61a16884d0bbe1c17adad363ae995），日志`.cache/studio-resume-ui-journey-final2.log`退出0。更长隔离素材经真实普通Planner与同一知识/动态采用链，Studio实际显示narration-script的知识句及出处；编辑后剪贴板/TXT逐字一致，刷新恢复、语音POST为0，1440/1280宽度无横向溢出。截图、browser-evidence.json、summary.json、planning-evidence.json和result.json均在`.cache/scratch/resume-ui-journey/`。
5. 上述Studio同库链随后生成真实360帧/30fps/12秒MP4及七文件ZIP；静音源、无BGM、旁白start30/gain-6/ducking off。解码1.25–1.75秒窗口880Hz幅度0.24470486、440Hz幅度0.0000002475，满足>0.01与>5倍条件。包localChecks pass，publicationEligibility unverified，平台规则/来源权利/人评保持unknown。
6. 旧v1磁盘兼容：基线8ea3293服务源码在当前基础依赖中生成prepared record，由当前服务回读/执行/采用/重复采用及新实例重开，record不变、实际user逐字一致、fake仅1次，保持v1 prompt。证据`.cache/studio-resume-legacy-v1-final.log`及`.cache/scratch/legacy-v1-compat/result.json`；未读取或重发用户历史付费记录。
7. Studio真实图片/PDF输入：`.cache/scratch/studio-real-knowledge-media.py`（SHA256 `972e8440cc8122184e785eacc8b37bb9867638178edee89f06b182af54f1db68`），日志`.cache/studio-real-knowledge-media-final.log`退出0。本机生成PNG及单页PDF，经真实Windows OCR/Windows.Data.Pdf和Studio文件输入各保存一次；搜索/全文显示识别文字及“文字由本机OCR识别，可能有错字”来源说明，语音任务0。结果和两张详情截图在`.cache/scratch/studio-real-knowledge-media/`。使用既有隔离timeline夹具；未验证多页截断提示或目录媒体批量导入，不能扩大成全部格式/页数验收。
8. 目录导入ABA隔离（R38）：`.cache/scratch/studio-import-scope.py`，SHA256 `deb223cf5718f5d42953a1b58283a4783488359f4e1b6b697e2e9dff4219e3f3`，日志`.cache/studio-import-scope.log`退出0。浏览器挂载实际KnowledgePanel，实际目录API已完成写入后挂起响应；game A→B→A，新导入等待时释放旧成功或注入旧HTTP500，当前busy不清、旧结果不回流；新响应只显示new.txt。每例两POST，原游戏两条知识保留，无自动重试。注入500模拟传输失败，非声称真实后端拒绝；是组件作用域验收，不是整个Studio换游戏点击流程。结果`.cache/scratch/studio-import-scope/result.json`。
9. 旁白跨项目与丢响应重试（R28）：`.cache/scratch/studio-narration-scope.py`，SHA256 `cf21250c83332aef254ccbb567f3c708e04445e0a070ef5fe37a6a42f0b9987a`，日志`.cache/studio-narration-scope-final.log`退出0。在真实Studio项目下拉切换A→B，A重合成的迟到成功/注入HTTP失败均不清B合成busy，不覆盖B正文；B挂接后起点仍0帧。另在实际接受任务后模拟响应丢失，用户手动重试的requestId/jobId完全相同，唯一新任务1个。旁白引擎仍明确fake、接口/回执/作用域实际执行；结果`.cache/scratch/studio-narration-scope/result.json`。

## 完整门禁与集成

源码检查点51cd54c、测试适配41ff654已推开发线；P020独立合并baf2a20、规范独立5809705。本批按最终完整门禁结果快进集成，保留开发线。

完整门禁`.cache/studio-resume-final-verify.log`（60190）终态5093通过/4失败/7跳过，1778.94秒；静态通过，CLI未执行。4失败为旧定位/草稿恢复契约/货币字形/import子串检查的测试适配，业务源码哈希不变。修后原4项组合4通过11.63秒，shell补注释与无空格导入回归后全4项通过1.79秒，唯一关键审查者补审通过。证据`.cache/studio-gate-fixes-combined.log`及`.cache/studio-shell-import-guard.log`。最终重试`.cache/studio-resume-final-r2-verify.log`已通过：**5098 passed /7 skipped，1760.46秒**；493文件格式/Ruff/mypy209源及CLI全过，session52192终态0。520源码/测试完整匹配`.cache/studio-resume-final-r2-freeze.json`；不为后续文档/证据同步重复全量。未跑Release，不代表分发或人评通过。前序受影响测试于12%及完整门禁于63%主动中止以修复审查发现，不作通过证据；原日志保留，不覆盖。此前全量5066日志还有源码临时误写窗口，仅作历史诊断。

## 仍未证明

规则/准备/采用/修订/渲染使用实际服务接口，旁白编辑、跨项目隔离与知识文件输入经过浏览器，不能声称所有步骤均已通过Studio点击。源/时间线为隔离合成夹具，模型/本机声音为明确fake；真实AI、音色质量和用户录像创作质量均未验。媒体目录批量导入、多页提示与完整双尺寸专项等原工单剩余项继续保留；不以本批证据标记整项交付、人评或真实平台发布通过。
