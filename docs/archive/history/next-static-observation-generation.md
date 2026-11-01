# 下一项草案：单个注册帧自动生成静态观察

2026-10-24，Astra/low只读设计返回，主控收敛，尚未实施／绑定合同／创建新DSH对话。用户提醒额度剩约12%，要求做完手头后暂停；当前静态导入／查询已完成81216a5，本草案只作下次接续输入，不继续派发。

## 目标与最小闭环

每proposal只选一个当前Completed run的已注册帧，显式collection/profile。生产流程为prepare冻结精确身份→显式新授权下至多一次dispatch→严格静态解析→持久化typed结果及真实调用metadata→复用现有不可变collection发布→另一进程typed查询。无主体的合法结果保存no_observations，不伪造空主体或动作事件。真实Provider接受性与视觉准确性仍待独立验证。

准备阶段无网络；真实执行须另有具体proposal／图片／参数／金额及人类授权。用户补六视频仅登记可用，不成为付费许可；本次没建立真实授权文件，也没排入发图队列。开发仅合成注册图、真实SQLite与fake transport，不需用户重新标注。

## 已确认复用边界

- 可复用VisionTransport／HttpxVisionTransport、ProviderResult／InvocationMetadata／ProviderUsage、取消上下文及纯BudgetLedger计算；新静态包／导入验证／独立SQLite与查询保持。
- 旧deepseek_detail_refinement依赖event_id，旧detail budget的charge／恢复硬编码候选prompt/schema/stage及目录。不得伪造Event／CandidateDetail借用，不将新占用写入旧身份。
- 新独立StaticObservationProvider、request/profile/prompt/schema/hash；模型只给当前帧主体／部件／五种冻结静态属性，不能给路径、时间、run/event身份或动作。程序注入已验证源时钟与绑定。
- 项目架构禁止保存原视觉响应：响应只在内存中有界解析，持久化经过严格校验的typed载荷、调用metadata及白名单诊断／原响应SHA和大小。崩溃在响应返回但本地结果落盘前时仍保留planned未知，不通过保存任意HTTP正文规避恢复问题。

## 新授权与恢复

建议使用静态生成专属不可变授权，明确proposalHash／金额上限／请求数1／图片数1；旧费用、原unknown和旧授权不变。此为新授权池，不声称与旧精分析已有授权双向统一；若需同池，先另立旧reader／sender双向一致的设计，不能只做单向读取。

固定项目级静态授权账本与锁；同授权下换collection、输出目录或重启不能清零占用。planned在发送前持久化且足以重建预留；known按同attempt只结算一次，unknown保留预留与发送次数。已知实际估价超出上限照实记，不截断。预算锁不跨HTTP，request锁覆盖一次执行；成功重复执行零新发送，恢复只补本地发布，不提供自动重试。

## 拟文件归属及验收

未来单个DSH写application/static_observation_generation.py、static_observation_budget.py，infrastructure/deepseek_static_observations.py、static_observation_attempts.py，cli/static_observation_generation.py及main注册；按需仅改旧静态报告的一句claim说明，不改其schema或视觉已核实标志。另加generation／budget／process测试。公共docs／合同／正式测试／Git由主控；唯一Sol/high在派发前核费用／恢复合同。

验收须是真实存储与生产入口，fake transport全链路，非mock Store：同请求／并发最多一次发送，planned/timeout未知不释放，响应／解析／发布各崩溃点恢复不重发；版本／source/evidence/hash／源时钟变更拒绝；损坏账本失败关闭；坏JSON／动作／异帧／超限／HTTP失败无假观察但保留费用；旧timeline／费用／标注／V6 hash不变。报告仅宣布离线流程贯通，F006/F009/F010false。

恢复顺序：先读HANDOFF并核当前STOP_PENDING，不重投旧三个请求；确认原生后台活动后，核当前Git／环境及本草案，形成完整合同并经唯一评估，再在同workspace新对话实施。当前未评审新合同，不以设计稿当作实际开发完成。
