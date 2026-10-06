# F010/TD009：从描述生成可编辑条件草稿

2026-10-06，root / Codex，codex/visual-details，基线e7dab08。前一切片1283/1权限skip已验证并独立核对远端e7dab08；详细汇报见report-2026-10-06-temporal-details.md。用户要求继续按计划开发，当前只做离线工作。

## 用户效果与范围

用户输入“白发、红色外套、拿着蓝色扁平物体”等描述后，得到可编辑的发色、衣物和持有物条件，确认后核对已保存结构。不能识别的文字单独显示；不能默默遗漏角色名、技能、否定、或条件、多个角色关系等要求后宣称整句满足。原自然语言召回和source rank不变，草稿不证明内容匹配或理解准确。

第一版是明确支持的正向同主体语法，使用冻结词表，不调用模型。支持中文和明确英语短语、同一衣物颜色/形状组合、多个不同衣物/物品的独立部件组及环境条件。查询-v1、词表-v1继续冻结；新草稿输出单独版本actor-detail-query-draft-v1。未支持结构不自动降级为关键词AND；原句、识别片段和未识别片段都保留。

## 处理与确认

1. 新纯Application解析器最多接收2048字符，返回版本、原句、status、识别条件manifest或null、逐段accounting和未处理片段/原因。偏移明确按Unicode code points；网页直接显示片段文本，不按JavaScript UTF-16盲目切片。
2. 只有有非空actor条件且所有实质文本都已处理，才是ready。未知文字为needs_review；否定/OR/多主体/关系/时序等不支持结构为unsupported，不提议可能改变原义的肯定manifest。空句、只有环境、超16条件不得悄悄截断。
3. 中文颜色＋衣物名构成同一部件组，多件衣物/物品分组。发色、动作和效果沿用冻结kind/value，引用词表之外的技能/名称继续未处理；不从自由词虚构新value。
4. 本地草稿API只解析正文，不访问SQLite、文件或Provider。UI填入草稿后由用户修改/明确确认，不能生成草稿同时运行匹配。未处理片段存在时只有明确选择“仅核对已识别部分”才允许子集核对，结果始终说明原描述仍有未核对要求，不能称原句全部满足。
5. 编辑原句、重新生成、关弹窗、切run/profile都使旧草稿/响应失效。原typed手动模式继续可用；不新增API费用或修改原事实、账本、篮子与导出身份。

## 分工

- detail_cost_history接续新worktree `.worktrees/detail-query-draft` / `codex/detail-query-draft`：独占新 `application/detail_query_draft.py`、`tests/test_detail_query_draft.py` 和own sprint。旧cost worktree冻结，不改其他文件。
- root：新草稿API、UI确认/未处理内容展示、集成测试、共享文档与最终检查。先集成worker接口，再串行接入。

## 验证与限制

测试覆盖未处理名字/技能、否定/OR/多个角色/时序、环境-only、未知颜色/部件、重复/条件上限、同衣物绑定、不同衣物不拼接、Unicode/安全文字和稳定accounting。浏览器验证编辑/确认/部分要求提醒、迟到响应隔离、手动条件兼容、零Provider/账本写入。实际用户长句语义覆盖仍有限，F006/F009/F010不能由这些测试转true。

## 已汇报与下一步

整合检查点：worker623fca1→f30e812及语义修复f5aef6f→85fa5a0已整合。定向197 passed/39.23s，.cache/detail-query-draft-final-targeted.log；init完整环境检查通过，.cache/detail-query-draft-init.log。只读审查发现生成响应前可提前确认遗漏的问题，已禁止生成期间确认并在新结果清零；null/unsupported保留原手动条件与组，不丢用户编辑。“没/未/doesn't/instead of”、前后时序不产肯定条件，同一长杆武器不拆组；新28反例在134解析tests中。root22 HTTP/browser与旧queryHTTP、18proposal组成联合检查，未知Unicode/HTML原文、组保留、提前确认、迟到草稿和零写/零发送通过。完整verify待本检查点后运行。

真实已有28–29秒片段：桌面1366/手机390生成蓝发/红外套/蓝扁平物体，旧v2匹配partial；未知“恶魔领主”保留原文并需明确确认，v4缺结果unverified，0页面错误/外部请求/Provider。源表/侧车/proposal SHA不变，query-draft-browser-report.json与两截图在artifacts/detail-temporal-validation；已视觉核对桌面图。结果范围持续说明仅当前条件，支持帧按钮也限定“上方有支持条件”，不暗示部分命中满足全部要求。

已向用户说明生成只填条件、不自动匹配；未处理原文和子集范围持续可见，下一步检查编辑/关闭/切run/profile与迟到响应。同步说明v4对照清单已冻结但不发送，旧许可耗尽且无新费用。方案worker ac72b4d→34135cc，root本地dry-run再验通过，见own sprint与.cache/detail-temporal-proposal-read.log。

已向用户生成并链接上轮详细报告，解释本轮目标是减少手动加条件而保留未处理要求。下一步实现纯草稿及本地确认流程；v4真实对照仅准备方案，旧两次调用授权已用完，不额外发送。
