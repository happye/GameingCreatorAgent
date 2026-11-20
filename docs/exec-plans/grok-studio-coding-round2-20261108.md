# 给 Grok 的第二轮开发工单：核心接入、旁白可编辑与真实制作闭环

日期：2026-11-08。48项，按依赖持续实施。任务量不代表必须消耗多少时间；以代码和验收证据为准，不以重复测试、报告篇幅或自评分凑工作量。

## 交接判断与本轮目标

第一轮6文件SHA256已由接收方核对，均与T32报告一致。但第一轮有5项未完成、1项部分实测，且静态审查发现4个真实UI缺陷。Codex尚未收口的知识策划核心另有1个Unicode截段缺陷。本轮先修这些明确问题，再接入已写好的核心代码，完成更重的业务功能与真实制作链。

已有报告的7个测试通过不能视为32项全部验收；86/100、68/100等未约定自评分不作验收依据。接收方按项目默认命令检查`mypy src/gamingcreator/ui/server.py`已通过，不要为了第一轮额外使用`--follow-imports=skip`产生的Any错误修改无关业务代码。

最终用户能力：

1. 已有知识真正进入动态策划请求，采用后引用可回读。
2. 已挂接旁白可以编辑文字、恢复本机稿件、用本机声音重新合成，再保存为新版本；失败保持旧音轨。
3. Studio可用已有接口批量导入知识目录，逐文件结果和失败清单可读。
4. 隔离环境走通“规则/知识→策划→旁白修改→新版本→真实MP4→本地七文件包”。

## 固定授权与禁止事项

- **禁止修改任何Harness。** AGENTS.md、CLAUDE.md、CODEX.md、HANDOFF.md、STATUS.md、feature_list.json、.codex/、.claude/、.grok/、.github/、skills/、.learnings/、Hooks、路由/模型配置、scripts/、tests/conftest.py、pyproject.toml、uv.lock及现有计划/规范文档全部只读。本工单也只读。只允许下面具名业务代码和业务测试。
- **只实施，不做设计。** 接口、行为、迁移方式和验收已固定。不建新API、数据库、通用状态框架、费用流程、检索引擎或任务调度器；不重构现有收费/账本/调用锁。函数局部写法自行完成，新增函数遵守现有≤80行约束；确实缺接口时报告任务ID和文件依据，继续其他独立项。
- 原自主Goal已清除，本次只授权本工单；不自行创建或恢复全项目Goal。做完或用户叫停后交回，不继续新功能。
- **不跑完整测试、verify.ps1或Release。** 日常跑受影响场景；本轮稳定后统一跑指定业务组合。最终完整门禁由接收方在整批代码与关键审查闭环后安排，报告记录未跑原因。
- 不真实发送云端模型/图片/付费语音，不启动PR/AE，不安装依赖。新增重合成路径只支持现有本机声音；原有付费路径保持原协议，不能被新增路径自动触发。验证用fake文本模型及fake本机语音引擎，允许现有FFmpeg处理隔离合成媒体。
- 不改原录像、用户知识/项目数据库、账本、已保存证据和旧报告。测试数据放现有隔离fixture；不向用户真实知识库写验证条目。
- 不停止8765–8769，不自动打开桌面程序，不把旧服务当新代码证据。

## 工作位置与Git边界

唯一写入工作区：`G:\Tools\ChatGPTRepo\GameingCreatorAgent`。每个exec显式使用该workdir；写文件使用根目录下绝对路径。Python前`. ./scripts/env.ps1`，检查`gamingcreator.__file__`确在根目录`src`，不在子树。

当前HEAD/main为8ea3293，根目录有MERGE_HEAD d28d668及既有暂存P020内容，也有第一轮6文件改动、规范/设计稿等其他工作。**保留所有现状，禁止Git写操作：不checkout/reset/clean/stash/merge/add/commit/push，不改index、不处理旧merge。** 只用status/diff/show等读取。第一轮文件不要重写成旧版本。

只读迁入来源：`G:\Tools\ChatGPTRepo\GameingCreatorAgent\.worktrees\j1-preview-corrections`，分支`codex/planner-knowledge-20261108`，基线8ea3293，有7源码+3测试未提交改动。它是Codex待收口成果，**只读，不能在那里写入或运行生成数据的验证**。迁移用相对于8ea3293的具名文件差分，先检查再应用，不能复制整棵树或覆盖当前edit.js。

## 18路径写入白名单

| 业务范围 | 允许路径及限制 |
| --- | --- |
| 知识选择及v2方案 | `src/gamingcreator/application/knowledge.py`、`plan_proposals.py`、`plan_reasoning.py`：迁入既有差分、修R14；不得新增模型或改排序/预算策略 |
| 模型边界 | `src/gamingcreator/infrastructure/creation_reasoning_provider.py`：仅迁入已批准的plan v2 prompt/schema匹配白名单项，不改发送/费用/计费/锁 |
| 策划服务 | `src/gamingcreator/ui/creation_reasoning_service.py`：迁入既有冻结资料/投影差分；不能查新库替换已批准请求或改旧记录 |
| Studio业务 | `src/gamingcreator/ui/static/studio/audio.js`、`knowledge.js`、`planning.js`、`edit.js`；保留第一轮工具、P020活动规则和P033下载 |
| 本机文字草稿 | 新增`src/gamingcreator/ui/static/studio/narration_drafts.js`，仅R22–R24的浏览器产品草稿辅助，不是Agent记忆或Harness |
| 静态注册 | `src/gamingcreator/ui/server.py`仅给新narration_drafts.js增加一项静态映射，保留activity.js/knowledge.js；不改业务API |
| 既有业务测试 | `tests/test_knowledge.py`、`test_plan_reasoning_jobs.py`、`test_studio_planning_browser.py`、`test_studio_knowledge_browser.py`、`test_studio_narration_tools_browser.py` |
| 新业务组合测试 | `tests/test_studio_narration_revision_browser.py`、`tests/test_studio_tools_journey_browser.py`；复用fixture，不改conftest或新增测试框架 |

同一表格行中省略目录的文件与该行首个文件同目录。白名单外只报告，不擅自编辑。证据统一放`.cache/scratch/grok-studio-round2-20261108/`，保留第一轮证据。

## 固定实现选择

### 知识策划

- 迁入既有v2实现：当前同游戏匹配知识最多3条，每条最多400个原文字符；冻结entryId/title/source/createdAt/原文片段入实际request.user及hash。
- 无知识沿原v1字节、prompt/schema和hash；有知识使用既有实现中的plan-reasoning-prompt-v2/plan-proposal-v2配对。不发明第三版。
- execute/adopt/recover从prepared record的冻结request恢复知识，仍重验原job、原片和候选；不重新查询最新库。不改保守报价算法或账本。
- knowledgeUses只接受entryId/structureQuote，出处由后端从冻结资料补齐；引用对应关系不等于资料真实性或模型语义正确。

### 旁白编辑与本机草稿

- 已挂接旁白显示“编辑旁白文字”。点击只打开本机待合成稿，初值为asset.text；旧音轨继续有效，直到新本机合成成功且适配当前时间线才替换。
- 新的编辑/重合成路径仅允许paid=false的现有本机声音。原付费逻辑不改，不让新按钮绕过既有确认。
- 本机草稿使用localStorage；单项key为`studio-narration-draft-v1:`加`encodeURIComponent(JSON.stringify([projectId, baseJobId, planId, attachedAssetJobId或空字符串]))`。不要把game或显示标题当身份。
- 值固定为`{schemaVersion:"studio-narration-draft-v1",text,voiceId,updatedAt}`。只保存文字及声音选择，不缓存批准信息、费用、引用证明、回执或媒体。恢复时显示“已恢复本机未合成文字，来源需重新核对”，不能把恢复文本当成已合成资产或已核引用。
- 输入变化保存当前scope。作用域切换不得把旧内容保存进新key；不自动遍历、清理或淘汰别人的草稿。quota/JSON损坏时保留当前输入/原存储，提示可复制或TXT导出，不重试循环。
- 只有明确“清除本机草稿”并确认后删除当前key；不删其他scope，不移除已保存音轨。
- 重合成期间保留旧asset及原startFrame/gainDb/ducking，锁定本条旁白的参数编辑/移除/重复提交，允许预览和复制。新任务成功后复用`narrationProblem`检查适配，再一次性用新assetJobId/receipt替换，同时保留原位置/增益/闪避和整个mix。
- 合成失败、结果不适配、请求身份过期均不替换旧音轨、不清文字、不自动重发，不删除新旧资产。UI请求成功/catch/finally和forgetIntent都必须仍属于当前请求；旧任务不能清除新任务的intent或忙碌态。
- 后端保存修订、恢复父版本和成片渲染继续使用现有接口，不新建旁白版本格式。

### 知识目录导入

只接现有`POST /api/knowledge-import`，JSON为`{game,directory,sourceKind,sourceLabel,includeMedia}`。game取已加载方案Brief，includeMedia默认false，来源类型沿现有3项。

响应已固定为`{schemaVersion:"knowledge-directory-import-v1",directory,includeMedia,items,summary}`；items逐项含file/status及entryId/title或reason；status为imported/skipped/failed，summary含imported/skipped/failed/considered。后端已规定只读目录直接子文件、最多50个候选，文本/Markdown默认、图片/PDF可选。只做UI，不改后端目录处理、去重、容量或链接策略。

不要做虚假百分比进度、后台队列、自动失败重试或递归导入。等待时显示“本机导入中”；切换界面不代表已接受的导入被取消，旧结果不能污染新scope。

## A. 修复第一轮缺陷及剩余验收：R01–R10

| ID | 编码任务 | 明确验收条件 |
| --- | --- | --- |
| R01 | 保存期间禁止结果入口改写表单 | 两个“修改并保存新版本”入口都受saving限制，beginEdit内部也有保护。延迟保存A时点击B修改，表单不变；A完成后不能清掉B的新内容；只发1个POST。 |
| R02 | 修复同一文件连续保存 | 成功时同时清file状态和原生input.value或重建控件；拒绝时保留选择。连续用同一map.txt保存两个不同标题，两次都触发读取/保存，不出现“可见文件名但请选择文件”。 |
| R03 | 修复迟到历史覆盖当前全文 | 查看其他全文、新搜索时失效旧history请求，响应绑定选中entryId。A历史挂起→打开B全文→A晚成功/晚失败，当前仍为B，复制ID/正文也仍为B，新busy不被旧finally清除。 |
| R04 | 修复空白稿复制/下载 | 按trim后是否非空决定按钮可用性，实际输出不trim。`空格+换行+tab`两个按钮均禁用；` 前后有空格的正文 `可操作且输出逐字保留。已挂接资产同样执行。 |
| R05 | 补齐真实拒绝后的表单恢复 | 对新增和修改各制造1次真实后端拒绝；正文/文件/来源/replaces均保留，POST数为1且不自动重试；修正后用户手动提交成功。不存在代码缺口时只补必要业务断言，不重写模块。 |
| R06 | 落实文件前置边界 | 覆盖0字节、10MiB+1、.exe、大小写.TXT；前三个0 POST，合法.TXT可保存。后端拒绝超长读出文本时保留输入且无静默截断。复用同一场景覆盖多个条件。 |
| R07 | 完成知识搜索/保存ABA与晚失败隔离 | query更换、game A→B→A、卸载以及晚失败均不得回流旧结果；新请求busy不被旧finally清掉；旧保存可以在原game完成，但不能清当前新game表单。即使测试忽略abort也成立。 |
| R08 | 完成起草身份切换保护 | job/plan/project变化及A→B→A后旧draft成功/失败不能覆盖新稿，旧finally不清新busy。用有序延迟控制，不用任意长sleep碰运气。 |
| R09 | 完成图片/PDF输入处理的可证据部分 | 使用现有本机解析路径验证可运行的图片/PDF样本，来源说明带OCR提示，未读全页时沿后端提示。没有运行条件就列该格式“未实测”及原因，不装软件、不退云端、不把协议mock当真OCR通过。其他任务继续。 |
| R10 | 补上第一轮T31真实贯通 | 在同一隔离repo/服务里真实保存知识→真实检索→真实narration-script→显示引用→编辑→复制/TXT。不得用fetch直接假造citations。输出文本等于当前编辑框，语音合成调用数0。 |

## B. 接入Codex未完成的知识策划核心：R11–R20

| ID | 编码任务 | 明确验收条件 |
| --- | --- | --- |
| R11 | 迁入六个非重叠源码差分 | 从指定子树读knowledge.py、plan_proposals.py、plan_reasoning.py、creation_reasoning_provider.py、creation_reasoning_service.py、planning.js相对8ea3293的差分，检查后用编辑工具应用root。保留第一轮及P020内容，不复制全文件，不写子树，不改index。差分列表/来源必须可追踪。 |
| R12 | 合并edit.js的两处知识展示改动 | root已有ActivityRules和AudioPanel game属性全部保留；增加KnowledgeUses导入与PlanInspector渲染。活动规则、知识管理、动态引用、专业下载4类入口均存在，不能用子树edit.js覆盖root。 |
| R13 | 迁入三个业务测试差分 | test_knowledge.py/test_plan_reasoning_jobs.py/test_studio_planning_browser.py的现有子树新增测试进入root；保留第一轮两个新测试和P020测试。用实际新增差分核对，不重复造一套fixture。 |
| R14 | 修复Unicode casefold截段错误 | 将casefold匹配位置映射回原文字符索引再截原文，保留现有排序/3条/400字符限制。`text='ß'*900+'needle'`、topic=needle时片段非空且含needle；补长度变化字符回归，如İ。每个片段均为对应原文连续子串，不在展开后的字符串上切片。 |
| R15 | 保持无知识v1身份 | 无条目或零命中时，v1 snapshot/request/fingerprint/requestHash逐字保持原值；现有v1流程继续可准备、确认、采用。不能为方便统一升级所有请求成v2。 |
| R16 | 落实报价后的冻结资料 | prepare后保存知识新版本，再用fake transport确认，捕获实际request.user与quote逐字相同、仍引用旧ID/原文；新prepare才引用新ID。不变更报价/价格快照/确认门禁。 |
| R17 | 落实v2引用拒绝边界 | 合法引用成功；未知ID、重复引用对、structure中不存在的原句、模型伪填source额外字段均被拒；knowledgeUses空数组允许。实际代码已有时复用，仅补缺失的代表性断言。 |
| R18 | 接通引用预览、采用、重开 | 结果预览与采用后重开都显示同一entryId、structureQuote、冻结资料原文/来源。重复采用不增加发送；引用原文以文本显示，不执行HTML；0命中明确显示没有发送资料。 |
| R19 | 保持原媒体与候选校验 | 原视频字节或候选事实变更后，确认发送前/采用前仍拒绝；前者fake传输发送数0，后者不登记新采用任务。不为冻结知识跳过原验证。 |
| R20 | 补可回读的旧v1磁盘证据 | 用现有格式生成独立的旧v1 prepared/result测试夹具，再用新代码read_result/采用；不是把v2删字段假扮v1。旧文件前后hash不变，读取/采用不新发送；不要读取或修改用户旧付费记录。 |

## C. 真正可编辑旁白及本机稿件恢复：R21–R30

| ID | 编码任务 | 明确验收条件 |
| --- | --- | --- |
| R21 | 已挂接旁白文字编辑入口 | “编辑旁白文字”打开待合成稿，初值逐字等于asset.text；旧音轨、选择参数、mix和dirty状态不因打开而改变；0任务POST；待合成稿与正在使用的音轨区分显示。 |
| R22 | 实现具名本机草稿辅助模块 | 按固定key/envelope保存text与voiceId；草稿无模型/费用/回执字段；仅操作当前scope的localStorage，不写文件/数据库或新增Agent记忆。加载新JS资源200，静态映射只有所需新增项。 |
| R23 | 输入保存与刷新恢复 | 手写、模板编辑、已挂接资产编辑3条路径均可恢复文字；刷新保留最后输入字符；不同project/job/plan/asset不得串稿；恢复不自动合成/保存版本，来源显示为待核对。 |
| R24 | 草稿异常与明确清除 | 损坏JSON/未知schema/storage拒绝不能清空当前输入或其他记录；提示可复制导出。清除需确认，仅删当前key；取消则存储/文字不变；已保存音轨保持原样。 |
| R25 | 接入本机重合成操作 | 只对用户明确点击的当前待合成稿提交；paid声音禁用该新增路径并解释。期间保留旧asset、锁定本条参数/移除/重复提交，预览与复制仍可用；不复制一套收费逻辑。 |
| R26 | 成功后保持位置与混音参数 | 新资产合成成功且fit检查通过才调用一次现有narration编辑操作；新assetJobId/receipt正确，原startFrame/gainDb/ducking和完整mix保持；至少一例mix含真实已登记的非空BGM，不能默认归零或丢BGM。 |
| R27 | 失败和不适配保留旧旁白 | failed/interrupted/HTTP错误/新资产过长4类结果均不替换旧asset、不清稿、不自动重发；控件恢复可用，错误说明明确；新旧资产记录均不删除。 |
| R28 | 重合成晚返回与单次意图归属 | A任务运行时切scope并发B，A晚成功/晚失败不影响B音轨/忙碌/intent；丢一次响应后手动重试同意图只得到一个新任务。仅当前拥有的成功请求可forgetIntent，不能改api.js全局策略。 |
| R29 | 编辑退出与稿件保护 | 取消文字编辑不移除旧音轨，保留本机未合成文字；再打开能继续编辑。只有R24明确清除才删缓存；旧asset未被替换时不存在隐式版本保存。 |
| R30 | 新旧修订回读 | 重合成应用后用已有保存版本流程创建新修订；新修订指向新asset，原修订仍指向旧asset。来回打开各一次均回读正确文本/位置/混音，原job/回执文件hash不变。 |

## D. 知识目录批量导入：R31–R38

| ID | 编码任务 | 明确验收条件 |
| --- | --- | --- |
| R31 | Studio目录导入表单 | 知识面板内新增目录路径、来源类型/说明、includeMedia复选框及明确导入按钮；game取当前方案；includeMedia默认false，展开/编辑表单0请求。复用现有接口，不加目录选择后端。 |
| R32 | 提交与加载控制 | 有效输入点击一次只POST一次；处理中禁重复提交；不伪造百分比或逐文件实时进度；无game/空目录本地拦截。仅显式点击提交，不随刷新、切换或恢复自动POST。 |
| R33 | 严格显示真实汇总 | 只用返回summary显示导入/跳过/失败/候选数，四值与原始响应一致；识别现有schema；响应错误时显示失败，不造“全部成功”。目录与OCR说明原样以文本呈现。 |
| R34 | 逐文件结果及筛选 | 每个item都显示file/status及title或reason，可按三种状态筛选；列表条数与summary一致；失败项没有伪造entryId，成功项可打开已有全文详情。 |
| R35 | 真实5文件目录导入 | 使用全新隔离知识库及目录：01-a.txt与02-b.md正文不同、03-copy.txt同a、04-empty.txt为空、05-too-long.txt为20001字。首次结果恰为imported2/skipped1/failed2/considered5；UI与后端记录一致。 |
| R36 | 重导与目录错误 | 同目录第二次恰为0/3/2/5，不新增重复条目；空目录显示候选0；不存在目录或>50个候选时展示原拒绝，保留输入，不自动截取前50，不改后端限制。 |
| R37 | 复制/导出失败清单 | 只导出failed项，文件名knowledge-import-failures.txt；每项包含原file和reason；5文件样本恰2项，不混入成功/跳过；0额外业务POST，不自动重试失败文件。 |
| R38 | 导入结果scope隔离 | 导入A被接受后切B或A→B→A，A晚成功/晚失败不得替换当前列表/表单/忙碌；已接受导入可能继续处理，UI不能声称已取消。不得因迟到结果再提交；新请求POST数仍1。 |

## E. 一整批真实组合制作与交回：R39–R48

以下为组合验收代码，复用已有fixture；不是每行新建一个测试。允许一条真实流程同时满足多个任务。

| ID | 编码/验收任务 | 明确验收条件 |
| --- | --- | --- |
| R39 | 规则→普通方案→知识报价 | 同一隔离repo/服务，用真实规则API填入主题，生成真实普通plan；真实知识库登记对应资料，动态prepare可见正确引用。到确认前fake模型发送0次；不得fake掉规则/知识响应来凑串联。 |
| R40 | 知识动态策划→采用重开 | 使用明确fake文本模型返回合法v2；确认1次发送1次；实际请求含冻结知识且与quote一致；采用/重开/重复采用后仍1次。允许fake模型，不允许假造服务报告/收据。 |
| R41 | 采用方案→旁白来源及本机草稿 | 对采用版本真实调用narration-script，引用来自同一知识库，不用fetch伪造citation；编辑后复制/TXT等于现稿，刷新恢复不自动新建语音任务。 |
| R42 | 两个真实WAV与旁白修订 | fake本机引擎为两段不同文字产出可解码2秒WAV（旧440Hz、新880Hz），通过真实旁白任务/回执链挂接；在足够长的真实方案中起点30帧/30fps、gain=-6、ducking=off。重合成并保存新修订，原参数/原修订证据保持。fake语音不代表真实音色质量。 |
| R43 | 新修订真实MP4 | 用已有FFmpeg路径渲染新修订，不mock渲染；输出帧数与EDL相差≤1帧，30fps，方案总长≥4秒。隔离视频原声静音、无BGM；解码后1.25–1.75秒窗口880Hz幅度>0.01且>440Hz幅度5倍，证明新音轨进入成片。不得放宽断言/改生产DSP来凑通过。 |
| R44 | 新成片真实七文件本地包 | 同一render创建真实本地B站包；ZIP恰含video.mp4、cover.png、title.txt、description.txt、tags.json、platform.json、validation.json，视频可解码且引用本次render。保留真实Preflight/权利状态，不绕授权/改用户套餐/真投稿。若现有门禁拒绝，列准确阻塞，不改门禁硬造成功。 |
| R45 | 双尺寸交互回归 | 1440×900和1280×720下检查新增编辑、草稿恢复、批量导入、引用详情，document无>1px横向溢出；长内容只在原面板内滚动。键盘操作不误触plans/语音提交，文本原样安全显示。 |
| R46 | 最终定向组合与默认静态检查 | 代码稳定后统一运行本轮受影响业务测试，失败0，跳过逐项解释；旧已通过项不机械重跑。Ruff/format及mypy使用项目默认配置，不加follow-imports=skip规避/制造错误。不运行无参数pytest整仓、verify或Release。 |
| R47 | 冻结与差分核对 | 白名单外新增修改0；原index内容、规范、用户设计稿、子树与旧证据保持不变。列本次实际改动路径/最终SHA256，验收后改源码必须补对应定向验证。只读核对Git，不stage/commit/push。 |
| R48 | 最终交回并停止 | 写下述报告，R01–R48每项有状态及证据；复用证据可交叉引用。完整验证明确未运行且说明待接收方收口；真实云/付费调用0。未完成项不能写已完成，不以自评分或速度替代证据。报告后停止，不新开任务。 |

## 实施顺序与执行纪律

1. 先R01–R04修第一轮实缺陷；R11–R14迁入核心并修Unicode；R05–R10补原批次缺口。不能把已经存在的代码重写一次算新增成果。
2. 完成R15–R20核心相关校验，再做R21–R30旁白持续编辑与R31–R38目录导入；相关scope保护与功能同步实施。
3. 最后R39–R48在同一冻结代码上组合验收。接受已有通过证据，但不得把之前混合源码窗口的5066通过日志当本批门禁。
4. 每次命令明确根workdir；Python核根src导入。所有测试写隔离repo，真实媒体用合成短片且沿已有容量保护；不清理用户数据或旧失败现场。
5. 新问题只有在阻断本工单验收时才最小修复。其他问题列具体文件/触发条件交回，不顺手扩展架构、库、Harness或新语义模型。

## 回收报告

证据目录：`.cache/scratch/grok-studio-round2-20261108/`。

最终报告写入该目录`R48-handoff-report-20261108.txt`，并在对话给出文件路径。不得覆盖第一轮T32报告。

```text
工作目录/分支/起始HEAD：
原index/未完成merge/其他工作树是否保持：
实际修改文件及最终SHA256：

任务ID | 已完成/未完成/阻塞 | 实际代码改动 | 验收动作/命令 | 结果 | 证据路径
R01 ... 至 R48逐项列出，不能省略未完成项。

五个已知缺陷：修前触发条件、修后行为、证据
Codex知识核心：迁入路径、实际修复、v1/v2兼容证据
新增旁白能力：编辑/恢复/成功替换/失败保持/修订回读证据
目录导入：真实5文件首次与重导的四个计数
制作链：真实WAV/MP4/ZIP路径、帧数、音频测量、实际Preflight状态
定向验证：命令、通过/失败/跳过及原因、源码对应SHA
静态检查：项目默认命令与实际结果
完整验证：未运行，待接收方在整批收口后安排
真实云/付费调用：0（fake调用单独计数，不混作真实质量）
未完成/阻塞：任务ID、准确文件/接口、当前事实；不用“后续优化”概括
```

此工单不授权标记P018/P020整项交付、人评通过、分发就绪或费用已核对。代码能运行、fake技术链通过、真实模型质量、用户成片评价必须分开报告。
