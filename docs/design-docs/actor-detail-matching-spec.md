# F010：候选主体细节与复合匹配工程规格

2026-10-05；状态：待实现。依据 [F010计划](../exec-plans/sprint-visual-details.md)、[TD009](../exec-plans/tech-debt.md)、[Phase 0](../product-specs/phase-0.md) 与现有四层架构。
这是 F010/TD009 的最小切片；以下类型、文件和入口是实施合同，不表示已有功能或新增 HTTP API。
F006/F009/F010 继续 `passes: false`；有效 JSON、固定模板和开发实验均不代替独立人工验收。

## 目标与不变量

对已完成 run 的有限既有候选精分析，产生可追溯的镜头内主体属性，再离线判断复合条件是否全部成立。
原 `SemanticEvent`、raw facts、event/candidate ID、区间、证据、run configuration、既有 embedding 和篮子校验不改写。
默认搜索仍只执行本地 BM25/E5 与已有持久化；页面打开、刷新、搜索或恢复篮子不得隐式调用视觉 API。
精分析是显式发起的独立 Application 用例；第一版只处理关联visual事件的候选，复用该事件已引用且位于候选区间内的注册图像，不扩窗、不裁图或补采样。
静态属性只附属于既有候选；独立静态事件索引、跨镜头人物追踪与通用自然语言约束解析不在本切片。

## 类型与源时钟合同

Domain 使用 frozen dataclass/StrEnum，排除文件、SQL、厂商 SDK 和 I/O；Application 定义 request/result 与 Provider/Store ports。
所有时间沿用 `SourceInstant/SourceRange` 的整数微秒、媒体 duration 和半开区间；不得用秒数浮点或模型自算时间替代源时钟。

| 类型 | 必需字段 |
| --- | --- |
| `DetailEvidence` | 已注册 `evidence_id`、image sha256、`SourceInstant`；由程序加载，模型仅引用 ID |
| `DetailAttribute` | 主体内局部 `part_id`、`kind`、规范化 `value`、`status=observed\|uncertain`、`evidence_ids`、`source_range: SourceRange` |
| `ActorDetail` | `shot_id`、局部 `actor_id`、中性可见定位说明、`attributes: tuple[DetailAttribute,...]` |
| `ShotDetail` | 局部 `shot_id`、`source_range`、有序 `evidence_ids`、`environment: tuple[DetailAttribute,...]`、`actors` |
| `CandidateDetail` | base run/media/event/candidate 身份与 fingerprint、原候选区间、版本身份、`shots`、待核对说明 |
| `QueryConstraint` | schema/version、非空 `actor_all` 属性条件（kind/value/part_group）、可选 `environment_all` 条件；全部为正向 AND |
| `DetailMatch` | `full\|partial\|no_match\|unverified`、满足/缺失/不确定条件、对应 shot/actor 与证据；不输出概率 |

属性 kind 第一版固定为 `hair_color, clothing_color, clothing_shape, held_shape, held_class, action, effect, environment`，非法枚举拒绝。
kind/value 使用版本化规范词表和显式同义词；不按中文 bigram 的任意交集判定属性相等，不依赖 E5 分数证明全满足。
part_id 区分同人身上的外套/围巾/持有物；同一query part_group的颜色/形状/类别必须落到同一part，不能把红围巾+蓝外套拼成红外套。
模型选择支持帧 ID；程序生成属性范围 `[firstUs,lastUs+1)`，单帧属性为 `[t,t+1)`；属性在此范围外不自动延续。
引用须非空、去重、有序、属于冻结请求、同媒体、同 shot 且位于原候选区间；SourceRange/duration 与这些时刻一致。
shot 范围由其已引用帧生成，shot 之间不重叠；每个输入帧最多属于一个 shot，未归属或边界不明的部分保留待核对。
`actor_id` 只在 `shot_id` 内唯一；跨 shot 即使发色/衣着相同也不得合并或生成“该角色继续”关系。
同一 shot/actor/part/kind 的互斥 observed 值在重叠范围内冲突时不能完整匹配，记录结构冲突而非任取其一。
`action` 属性仍须至少两个不同时刻、不同 image hash；精分析不能解除 V4–V6 的动作/边界/静图保护。
模糊类别只记录 observed 形状，如“蓝色扁平物体”；“武器/权杖”若未确认则为 uncertain，不能复制进正面 tags/属性。
玩家/NPC控制不明独立标记；这不否认已观察到的发色、衣着或持有物形状。原 uncertainty 文本不自动变成属性事实。

## 复合匹配

第一版由冻结 manifest/调用者提交 typed QueryConstraint；现有自由查询继续检索，不能声称已自动解析同主体约束。
actor_all不得含environment；environment_all仅含environment条件，不能从环境记录借用另一个人物的外观或动作。
`full` 当且仅当存在一个 shot 内的同一 actor，其 observed 属性按part_group满足所有 `actor_all`，且同 shot observed 环境满足全部 `environment_all`。
所有用于full的属性支持范围须有共同非空交集，且交集内至少一个已引用帧同时支持全部条件（共享evidence ID）；仅first/last凸包相交不够。
missing、uncertain、未归属、冲突或跨 shot 属性均不能满足条件；未知不等于否定，更不能因 query 提及而补出属性。
`partial`只报告同一actor已满足子集；`no_match`须所有潜在shot/actor均至少有一项observed明确相斥，缺失/未知/未归属主体不能no_match；其余为partial或unverified。
strict 过滤只保留 full；普通候选可保留原 rank 并附 partial/unverified 说明，不得把局部命中标成完整复合命中。
query/matcher/schema 版本与 constraint hash 进入匹配报告；匹配本身纯函数、离线、稳定排序、零付费调用。

## 最小存储、幂等与读取

选独立 sidecar，第一版不增加 SQL migration：`<project>/runs/<runId>/detail-refinements/<requestHash>/`。
目录含不可变 `request.json`、追加式 `attempts/<n>-planned.json`/`<n>-result.json` 与校验后原子发布的 `result.json`；同 key 只允许一个写者锁。
requestHash 为规范 JSON SHA256：base run/media sha256/config hash/pipeline、event fingerprint/candidate ID/原区间、有序 evidence ID/hash/时钟、精分析 settings/prompt/schema/provider/requested model 身份。
event fingerprint 含原 raw facts/tags/uncertainty/区间/证据；base分析 promptVersion/hash 单列保留，精分析 prompt 不复用 V5/V6 hash。
精分析与 query 无关；成功的同 key 结果直接复用。失败/取消/中断不得自动重发，显式 resume 才增加 attempt，历史不覆盖。
恢复时先重验已完成attempt的typed输出并补发布result，不重发；同attempt的planned/result按一次调用汇总，不能重复计费。
result 保存 typed 输出、payload hash 与实际模型/revision（未知保持 null）；未知版本、非法 hash/类型或同 key 冲突拒绝读取。
每个 JSON 限 1MiB；实现前固定集合上限为9帧、9个shot、每shot8主体、每主体16属性，超限明确失败。
写入先临时文件+校验+原子替换；API 调用不持有 SQLite 事务。发出请求前落 planned attempt/预算预留，完成后原子结算。
Reader 仅接受项目目录内按计算 key 解析的文件，拒绝客户端任意路径/符号链接逃逸，先加载并验证当前 Completed timeline 与源/证据完整性。
读取须显式指定精分析settings hash和schema；同候选多版本并存，不按mtime挑最新或混用属性；缺图/非visual候选为unverified。
缺 sidecar 返回 unverified；损坏或源/hash/fingerprint不匹配返回明确错误，不能当 full、悄悄丢账本或使用另一 run 的结果。
搜索读取 sidecar不写原事件；匹配报告另存到相同目录的 `matches/<constraintHash>-<matcherVersion>.json`，不改现有 search record。
UI 后续只增附加匹配说明/证据视图；raw 篮子校验仍用既有事件，导出附加字段须明确版本，不能覆盖 observableFacts。

## Provider、费用与触发

精分析采用独立 `DetailRefinementProvider` port 和独立 prompt/schema/settings hash；不修改既有 `VisionProvider` 解析器或冻结 prompt。
初始图像合同沿用9帧/1280宽上限/3MiB每图/detail=original；实际支持、timeout和输出token上限进入 settings hash。
复用现有 `ProviderResult/InvocationMetadata/ProviderUsage/CostStatus/CancellationContext`；每次成功、失败、控制、取消都保留 metadata。
记录 provider/requested与actual model/revision、promptVersion/hash、schema、request ID、attempt、时长、token/缓存token、priceVersion 与估价。
执行入口必须显式选择候选/新实验目录、开启付费并给出 Decimal CNY 总预算；先无API冻结请求，不能复用旧实验目录碰运气。
同次任务固定`<project>/detail-refinement-budgets/<budgetId>/`会话/追加账本，跨run/key用预算锁串行恢复→检查→落预留后才发送并释放锁；换目录不能清零历史/unknown承诺。
沿用项目价格快照和保守 token 预留；每次 HTTP 前检查已知成本+未知尝试未释放承诺+当前最坏预留不超总预算。
unknown usage/cost/revision保持 unknown/null；无账单依据不得标 confirmed，失败请求不得计零；重试仍算独立 attempt。
断电/超时后的 planned attempt 按 unknown 保留预留；只能凭该次可核实 usage/账单结算，不能靠 resume 消除未知承诺。
精分析费用单独汇总，并报告与 base run 合计；缓存匹配零 API 费用，不能重复加算已复用 result 的原推理费用。

## 固定 fixtures 与真实实验

fixtures 是工程合同，以下观察来自开发材料，不是 human labels；具体 source run/evidence ID 由只读冻结 manifest 绑定。

| 组 | 输入与必需结果 |
| --- | --- |
| 1 同主体正例 | 同shot白发+浅色上装+抬头，证据/范围相交，full；换条件顺序结果一致 |
| 2 异主体组合 | Atom35s左侧白发/中间红外套；“白发 AND 红外套”不得full，同人的独立属性查询仍可满足 |
| 3 装备分类矛盾 | observed蓝色扁平物+uncertain武器/权杖；形状可匹配，类别不得full；重叠observed冲突也不得full |
| 4 跨镜头/缺失 | 两shot同发色分别有外套/动作不能桥接；黑发A+发色unknownB对白发查询不no_match；缺失不自动补全 |
| 5 时钟/证据边界 | 外run/未知ID/越界/乱序/重号/伪duration/无共同支持帧（含凸包相交）/单帧action拒绝或不能full；静态属性不得变动作 |
| 6 持久化/兼容 | 成功复用零API、显式重试留账、unknown不释放、跨key共享预算、并发/中断/坏hash/逃逸拒绝；旧raw篮子/JSON/CSV身份保持 |

真实试验共两候选，Atom源SHA为172e1139b477352db5e5fe2f3be3afb5171935c2edd8a2d0278a434212fd00fd；以下为只读SQLite实查事件，仍须冻结实际检索candidateId与图hash。
case-actors：V4 Completed run `96b5f01530ce43e2944828fb0520b9b4`，event suffix `861706cd8d81c59fe3e89543`，`[35000000,36000001)`，原引用image:000070/71/72，保持512宽输入。
case-item：V6 Completed run `f601fb9b3e734d5ea188fc15c790acbb`，event suffix `0b8be73b204cceb6f0e37c7d`，`[28000000,29000001)`，原引用image:000056/57/58，1280宽输入。
V6在35–36s无事件，case-actors明确用旧V4来源；逐case重验所属run/完整event ID/源范围/原引用证据，绝不跨run补帧，缺失记录source_missing，不造event或借failedV5。
每候选最多一次精分析HTTP（合计2次）、共享显式预算；失败不隐式重试，记录两个结果和全部费用/未知承诺。
35s比同主体正例与白发+红外套异人反例；28s比形状查询与武器/权杖类别查询，检查不确定性没有被query或模板强化。
对照保留base事实和原检索rank；人工回看原图/区间记录开发判断与错误，`humanLabels/qualityGate=null`，不能由Agent确认通过。
