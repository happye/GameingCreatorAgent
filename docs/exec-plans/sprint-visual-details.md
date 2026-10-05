# 可见细节与内部帧编号修正

2026-10-05；root分支codex/visual-details，起点72d692b。用户认可动作描述改善，但衣着/装备/其他人物/背景/Boss外观与招式细节不足，复合特征查询无法找回；f0/f1出现在正文，是输出处理缺陷。F006/F009仍未通过，不把本轮模型结果当独立人评。

## 已确认原因与范围

只读审查确认旧V4偏重动作，未系统要求人物绑定的细节；当前证据512×288，部分人物仅约40×70像素。Atom40事件中16条含内部窗口帧编号；parser仅映射evidenceIds，正文原样进入存储/检索/界面。事件uncertainty已存储，但界面漏传。E5最多512 token，描述不能无限扩张；当前RRF不保证任意复合属性同时属于同一主体。

改进使用独立V5 prompt、紧凑的主体→可见外观/持有物→动作/目标/特效事实句和1280宽证据（不放大超过原源分辨率），保留旧V1–V4/hash/run。只写看得见的属性，模糊/猜测留uncertainty；不虚构死亡铠甲、恶魔领主或官方技能名。暂不迁移领域/DB，仍保留多时刻/不同图像动作保护；独立静态外观索引需要后续显式事件类型，不能解除静图动作保护。

新V5知道完整窗口别名→源时钟，正文若泄漏会映射到真实时间后再生成事件身份。历史run只作显示/索引投影清理，不猜窗口时间、不改冻结事实；显示与导出保留选择校验。索引文本变化用新检索版本/文本hash，不能复用旧向量身份。

## 分工

- detail_vision：.worktrees/detail-vision，独占deepseek_vision.py/new detailed tests/own sprint；V5与分辨率/别名映射。
- detail_presentation：.worktrees/detail-presentation，独占observation_text.py、retrieval.py、ui/service.py、app.js/new presentation tests/own sprint；历史文本投影、不确定性展示、序列化清理及索引身份。
- root：配置/SQLite白名单/analysis版本与旧宽度保留、pilot真实对照、工程规格/共享记录、集成与验收。只读detail_pipeline_audit已完成，无改文件。

## 验证计划与恢复

先验证旧hash/512输入行为、V5宽度/输出/schema、真实alias映射和拒绝未知编号、主体细节提示、旧事实不可变/展示不泄漏/不确定性/检索hash。然后新有界真实窗口对照（冻结源/evidence/配置，预算¥5、费用全尝试记录），检验衣服/持有物/外观/背景与动作是否实际增加，不能把不存在的用户举例当素材真值。

小范围通过再创建完整新run供工作台测试，旧Atom/漫画保留。完整verify、真实浏览器/JSON/CSV、health匹配服务重启、跨工具文档/Git检查点。所有依赖只在项目.tools/.venv/.cache；当前未新API调用，无完成或效果声明。每个实现/失败/长任务前主动更新此记录与HANDOFF。

## 集成检查点

481d747保存计划，vision56b02e2已整合903c9cc，presentationa160116已整合86c229c。Root已补V5配置/SQLite白名单、独立phase0-analyze-detailed-v1与1280宽采样；V1–V4仍512。旧功能预期更新为V6未支持、能力1280；temporal/config/provider/resume联合252项通过，Ruff/mypy通过。

旧事实/别名/篮子/检索联合初次170passed/1skip/1failed：Windows随机端口1723被Chromium拒绝，未执行JS。修正共享测试listener为安全高端口后待复测，不隐去失败。detail_pilot独立.worktrees/detail-pilot负责新的同源时刻V4/512、V5/512、V5/1280与静图/倒序对照；root执行付费请求。仍未新API调用。GitHub443超时，工作分支远程尚未同步；本地commit已持久化。

复测显示/检索171passed/1skip，9.01s。只读复核发现V5正文可提到窗口里却未被事件引用的f8；已限制正文别名为该事件已验证引用（保留原窗口编号→真实时钟，不重排编号），新增facts/tags/uncertainty及区间内未引用/区间外6个回归案例。费用保护/旧512/raw身份未发现新增问题；复合属性AND匹配仍未实现。已确认DeepSeek API网络可达，GitHub443仍超时；不用失败模型请求探测网络。

真实实验前完整verify通过：838passed/1 Windows文件symlink权限skip，81.70s；Ruff83文件、mypy49源、CLI与两次离线wheel通过，SHA74728027088611445833fc4cb8802dbcaec8ca1a255b8357e0f91917c6bc459e。日志.cache/detail-verify-before-pilot.log。Guard单独98passed；尚未新增API调用，真实细节效果待对照。

预推理开发观察（不是独立humanLabels）：本地1280预处理已完成，artifacts/visual-detail-evidence-preview/receipt.json，未API。Atom35s画面有三位主体：左侧白发/单片眼镜/浅色上装/棕色短裤；中间红黑头发/头顶护目镜/红围巾与外套/深色手套；右侧较深肤色/红橙发/耳罩/蓝色图案上装。28s为蓝发角色/沙色石块平台/蓝色水面，手持蓝色扁平物的具体类别不确定。拟选28–32与35–39s对照，核对主体属性和动作是否绑定，不凭示例虚构权杖/冲击波/Boss。费用合计上限¥5：先pilot预算5，完整新run预算扣除pilot已知费用及未知承诺；全部失败/控制仍记录。

detail_pilot944fb42已整合32fe12c，9离线合同root复测通过（0.62s），脚本Ruff/mypy通过。真实无API dry artifacts/visual-details-atom-dry冻结两窗口10cases，A/B九帧完全相同512，C同源时刻1280，两组证据runId/hash独立。下一步只在新visual-details-atom-execute执行8HTTP上限/¥5/90秒每case，倒序不发送；不覆盖dry或旧实验。

真实对照 `visual-details-atom-execute` completed：A/B/C两窗口均3事件，两static空、两倒序发送前provider.input。8HTTP/72图，估价¥0.03676864，unknown0/reserved0；非账单、人评gate仍null。V5增发色/衣着/持有物/环境/光效，正文无alias；1280减少一些512歧义，但未保证准确：35s护目镜仍描述角状发饰/围巾色可疑，38–39sC声称室内跑向室外连贯，实际有剪辑。28sC武器分类不确定但正面用了“武器”；parser有效不能证实细节。全部结果保留，不仅报告改进。

下一步完整Atom新V5run，预算¥4.96323136（5减pilot已知及未知承诺），不重写V4。真实检索测试包含蓝发/白发/红外套/耳机/持有物/沙地平台与精确假设Boss负例，稀疏命中不计U10。后续候选精分析、切镜边界和装备消歧属于TD007/TD009。

完整verify含pilot847passed/1权限skip，82.21s，Ruff85/mypy49/CLI/重复wheel同747280...通过。首次完整V5run c78f204907e04eb3a2ac97a9017dcad9 在3/16窗口、8事件后因uncertainty字段合同错误停止；4HTTP估价¥0.0296662/unknown0，诊断仅有限枚举，无原响应，不能断言具体坏值。已完成窗口保留。按原配置/预算显式resume只重做缺失窗口，不放松事实/动作或猜修字段；失败费用留账本。

resume1补到9/16窗口、24事件后vision-000009的event_frame_boundaries失败；累计11HTTP估价¥0.07086276/unknown0，前3窗口没有重发。缺失端点/同帧/逆序具体值未保存，不臆测。继续显式resume2，合同保护和已完成窗口不改；本轮总已知pilot+run为¥0.10763140。

resume2同窗口再失败，有限数值诊断两次都startUs31500000/endUs31500001/eventIndex0，证实模型选择同一源时刻为首尾；不是未知坏值。停止重复V5，保留failed24事件/12HTTP总估价¥0.07282904/unknown0。新detail_v6 worker在.worktrees/detail-v6从e9183b3独占provider、新eligibility tests/own sprint，新增独立V6提示：先多帧主体动作后外观，单帧外观与纯切镜省略，输出前检查不同端点与引用。原V1–V5及parser保护冻结。root负责V6配置/独立detailed-v2/UI/pilot支持，新的V6run预算¥4.89040232（总5减pilot和失败V5承诺）。不把半成品V5设为默认Completed。

额度恢复接续：e26956a已保存未提交集成并将HANDOFF整理为单一当前快照。detail_v6_completion接着原worktree实现，dff948e→02cb7b2已集成；V6最终hash a60d114d9dd8bf82c5d2ea62c30c4cfe2b4316b08de34ade3cba883d6de9ea00，V1–V5不变，provider联合264passed/3旧版本断言排除（root均改V7）。Root合同/配置/恢复/pilot174passed（2.56s），真实dry visual-details-v6-atom-dry已冻结31.5–35.5s；尚无V6API。CLI普通/benchmark输出rawuncertainty+displayUncertainty、run-demo待核对列补齐，raw事实不变；定向94项先通过，benchmark新增持久化合同另测。

只读复核真实35s文本对“白发 穿红色外套”仍匹配（特征来自不同人物），证实TD009；uncertainty中孤立“权杖”不索引，但facts已误写“武器”时不会被不确定性自动纠正。后续须候选主体局部ID、observed/uncertain属性与证据、同人AND合同，不能用事件全文AND假装已解。GitHub本次只读重试仍443超时，尚无远端同步。

V6真实31.5–35.5对照 `visual-details-v6-atom-execute` completed：A/B/C均3事件，B/C跳过此前单帧31.5s事件，起止至少32–32.5s；static空、倒序发送前拒绝。4HTTP/36图估价¥0.01854028/unknown0。仍有待机/静态边缘：B第一段事实称没有明显动作，仅静态展示，C称轻微晃动，属性仍有颜色/配饰误认；不把格式成功当动作理解。Root继续完整新V6run，预算¥4.87186204（总5减两pilot与failedV5，已知合¥0.12813796），全部旧run保持不变。

## 2026-10-05 完整 V6 已完成；补交付验收

新 Completed Atom run `f601fb9b3e734d5ea188fc15c790acbb`，54.743220s，16/16窗口首次完成，33事件、0转录；V6 hash `a60d114d9dd8bf82c5d2ea62c30c4cfe2b4316b08de34ade3cba883d6de9ea00`，detailed-v2。模型估价 ¥0.10270124、unknown0、providerElapsedMs42467。本轮所有成功/失败/控制费用合 ¥0.23083920，在5元总上限内，不是账单。正文/uncertainty未发现独立fN，18事件有待核对。

最新完整 verify：876 passed / 1 Windows 文件 symlink权限skip，78.81s；Ruff86文件、mypy49、CLI、两次离线wheel。wheel SHA `5fc900a156bf27011c648f26b0c60ab4a944f6eaafc4396d24f6efd6614c7836`；日志 `.cache/detail-v6-verify.log`，分析日志 `.cache/detail-v6-atom-analyze.log`。代码c400188；查询/浏览器/生产服务刷新尚在补验收。

真实V6仍有问题：28s蓝色物体断言“武器”、32s轻微待机写成事件、38–39s切镜声称同一角色持续跑动。自由文本检索不能保证多属性同一主体（TD009）；actor-detail-spec worktree只写两篇新规格/任务文档。不放松动作/证据parser，不改旧run/facts/config；F006/F009/F010仍false。

## 2026-10-05 实际检索、工作台与下一合同

无API的10查询×lexical/semantic/hybrid已保存 `artifacts/visual-detail-v6-delivery/retrieval-matrix.json`，检索v5/投影v1；全部显示事实和待核对均无独立fN。jump hybrid2（0–2s/11.5–12.5s），指挥棒hybrid前3为15.5–17s/17.5–18s/17.5–19.5s；墨镜和场景有候选，汽车维修lexical/hybrid0而semantic10。用户恶魔领主/铠甲/权杖/冲击波复合例hybrid8，白发+红外套hybrid10：这是部分关键词召回/跨主体风险，不证明所有特征成立或U10通过。

真实Chrome验证：新run播放结束暂停、证据加载、篮子按时间排序、刷新恢复、JSON/CSV与1440×900/1366×768同屏、手机无横溢；`browser-verified/browser-report.json` passed/default新V6/33事件，无JS错误。首次报告default读到“正在读取运行…”；脚本已改为等待run/搜索/时间轴都加载后捕获，复测通过，无产品代码改变。

生产服务先重验health/状态与项目Python，只停止旧2548后启动38364/parent27896；Start-Workspace.cmd实际复用并打开浏览器成功。sandbox内打开浏览器曾Access denied，授权范围内升级重试成功；未改用户系统配置。生产fresh Chrome默认f601.../33事件/profile detailed，证据 `production-report.json`。临时诊断最初用了wait_for_function触发CSP unsafe-eval拒绝；已按现有脚本改调试器evaluate轮询，不放松页面CSP。旧V4及漫画timeline snapshot的SHA前后相同。

主体规格b1d91bc→a7789b4已集成；新actor-detail-contract worktree从00bc88f由detail_v6_completion独占5新文件，开发typed合同和纯同actor/part AND，不接UI/Provider、不调用API。需再验证共同支持帧、互斥冲突、unknown不作no_match和旧数据兼容；公共文档由root更新，F006/F009/F010仍false。

CLI实际脚本补验：run-demo -Run新V6 -Query指挥棒 -TopK3已返回真实前三候选，但PowerShell默认宽度把表格末尾“待核对”整列隐藏。改Format-List确保长事实和待核对均显示，TopK1实际复跑通过，无API/索引行为变化。此为可逆输出修正，未添加镜像格式测试；最终与新合同完整verify一起验。

## 第二段PV的独立V6细节分析（执行前检查点）

当前所有已知/未知承诺合¥0.23083920/unknown0。利用用户提供的第二段95.175874s漫画PV，在新项目artifacts/demo-visual-manga创建V6 run，明确使用config.detailed-v6.example.json、同hash/detailed-v2与隔离模型。新run最大预算¥4.76916080=本轮5减既有全部费用；含失败/unknown，不能跨项目重置总上限。原demo-phase0漫画V2、AtomV4/V6及其篮子不改；项目默认仍demo-phase0。仅补现有细节试验覆盖，不证明人评或新增渲染功能。分析日志.cache/detail-v6-manga-analyze.log；如失败先记有限错误，不盲目重试同窗口。
