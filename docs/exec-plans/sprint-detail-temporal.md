# F010：连续实体、持有物与切镜证据

本切片工程已验证：完整verify **1283 passed / 1 Windows文件symlink权限skip，126.74s**，Ruff118文件/mypy64/CLI通过；两次离线wheel同SHA `0cebff7f7ea68863d8df7a93f38f1d03aeb54041e1897f9b2e82bfe70a4c7e15`，日志 `.cache/detail-temporal-verify.log`。Worker81新测试包含实体/遮挡/owner/切镜；root新Provider与HTTP/桌面1366/手机390集成覆盖保存恢复、旧hash、费用/失败metadata、伪造投影拒绝、安全文本和证据回看。定向日志detail-temporal-targeted.log首轮测试snapshot导入及版本切换等待错误已修，不是模型效果证据。

集成：worker211bbf7→3278895；root添加v4 Provider、actor-details-v2/请求schema-v2/匹配matcher-v2、新4096-token settings与精确profile、完整scene持久和投影核对。旧v2/v3prompt/hash保持；真实两冻结候选v2 payloadHash不变，v4缺结果unverified，SQLite源表/侧车SHA不变、0新HTTP，证明见本地v4-read-report.json。生产旧PID已不存在，不停任意服务；启动当前新版16808/parent54620并核对api/health、状态和命令身份，真实33事件、v4新schema及旧v2payload读取正确，见production-v4-report.json。PID仅快照，下次须重验。

真实模型改进仍**未验证**；两次旧调用授权已用完、unknown ¥4.065536保留，F006/F009/F010仍false。原人工核对页面已展示用户反馈，不重新覆盖模型观察。

2026-10-06，root / Codex，`codex/visual-details`，基线766a80a。用户反馈见detail-human-feedback-2026-10-06.md；此前两个付费请求次数已用完，本切片仅离线开发，不新增HTTP或更改未知费用预留。

## 问题与预期使用效果

28–29秒物品被认成生物，三个连续帧被拆成三个单帧镜头。基础V6九帧中同样有误认，因此不能以增加帧数或v3部件嵌套当作修复。用户应能看到模型对角色、物品、未知实体及持有/遮挡/切镜的独立判断与引用依据；只把有角色资格和具体支持帧的属性送入同主体匹配。

## 实施前评审与版本边界

按Phase 0失败样本改善理解，先实现可核对的证据合同，再做真实模型对照。v1/v2/v3提示词、请求身份、旧payload与结果冻结；引入独立精分析v4身份及新响应合同。继续只使用候选原引用的注册帧，不扩大原范围或从另一run借帧。首轮不增加context-only帧；真实29→29.5秒切镜是后续独立对照，不能偷塞到当前28–29秒候选。

新请求每帧明示序号、注册sourceUs、帧间隔与候选原区间；模型只返帧ID，不生成源时钟。所有连续性和分类依据仍是模型判断，程序仅能验证合同与引用，不能证明视觉真伪。

## 新合同

- 每个相邻帧对都报continuous/cut/unknown和具体依据。cut须有两侧不同注册画面及场景变化依据；尺寸、旋转、特效、遮挡变化不能单独作为cut。unknown不连接身份；程序按这些边界划分连续段，不接收模型任意shot划分。
- 实体分actor/object/unknown，保留分类状态、依据、支持帧及描述。actor必须有角色结构或有连续证据的独立行为依据，不能用物品外观或被持有作为角色资格。未知不当作已排除人物。
- 实体逐帧记visible/partially_occluded/occluded/unknown与位置说明；支持区间内不能静默跳过帧。属性和分类不能引用完全遮挡或未知可见性的帧作肯定证据。
- actor部件只记发色、衣物、动作、效果；object部件只记物体形状/类别。持有物必须独立实体，并由有证据的owner关系投影给actor，不能借相邻位置推断持有。
- 持有关系必须同连续段、两实体在引用帧可见；投影属性只用物品属性与关系的共同支持帧。对象/未知实体不投影衣物或发色；未确定实体存在时，不能仅以已知人物相斥宣称no_match。
- 所有类型/枚举/引用/集合有界、不可变、严格检查重复与外来字段。保存分类、可见性、边界和owner依据，不能只丢弃错误对象而隐藏判断过程。

## 分工与集成顺序

1. `detail_parts_v3` 接续新独占worktree `.worktrees/detail-temporal-entities` / `codex/detail-temporal-entities`：新domain `temporal_entities.py`、application `temporal_entity_projection.py` / `temporal_scene_codec.py`、对应新测试及own sprint。旧parts worktree继续冻结，不改现有共享模块。
2. root：现有CandidateDetail/请求身份/侧车codec的版本化扩展，新独立v4 Provider、API/CLI/profile与页面证据展示、新集成测试及公共交接。先根据worker接口整合，再验证持久与浏览器；不修改冻结v2/v3。

## 验证

反例覆盖物品变actor、遮挡假切镜、真实切镜、unknown边界/实体、不同人物持有物、完全遮挡帧提供属性、跨帧/跨镜头owner、同图假动作、缺失/乱序/外来引用以及旧hash/费用/匹配兼容。工程结果只证明非法结构拒绝与正确证据投影；必须保留真实模型改进未验证。

真实验证将保留35–36秒三个正确主体正例、28–29秒物品遮挡反例和独立真实切镜对照，需要新冻结请求/明确目的地/预算及次数授权；不在本离线切片发送。

## 已向用户汇报与下一步

已向用户详细说明九帧基础分析也存在实体和切镜误认、用户反馈已独立保存，以及新页面可核对分类/遮挡/持有/切镜依据、未知不会当作已排除人物。本轮工程已通过，仍不能称真实误认已修复。下一步先冻结v4正反例对照请求与费用/次数上限，获新实验授权后验证真实模型；其间继续受控查询草稿。独立真实切镜对照需要合法原候选或另行版本化context-only请求，不能扩大当前28–29秒区间偷借29.5秒画面。
