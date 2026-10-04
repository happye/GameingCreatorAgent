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
