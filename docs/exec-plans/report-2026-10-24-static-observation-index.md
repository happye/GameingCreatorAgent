# 没有动作事件的画面可独立保存和条件检索

2026-10-23启动，2026-10-24完成，Phase 0／TD009离线工程交付。已有Completed录像的注册帧可以作为独立`static_appearance`声明导入，再按同人物／同部件条件查回证据图与原片时间。无需基础动作事件，不重标既有资料，也不把静图放进动作事件。这是已有声明的保存和检索能力，自动生成与真实外观准确性尚未验证。

## 使用效果与边界

生产CLI `import-static-observations`和`search-static-observations`要求明确project／run／collection及本地JSON。新库`static-observations.sqlite3`与原时间线分开，原库只读；同包重复导入复用，同collection内容变化拒绝，改版须选新collection。损坏、来源／证据不符、非Completed或覆盖缺口明确失败，不回退到另一版本或空结果。

单帧范围从已注册证据推导为`[t,t+1)`，输出图像路径、hash、源微秒及原片路径。同查询组条件绑定同一真实part；不同人物／帧／部件不能拼出命中。查询组名只是局部变量，来源组名只作声明元数据；同part的互斥观察跨来源组仍阻止完整支持。uncertain／缺失不能提供正向支持，非法unknown值拒绝。沿用五种静态属性及冻结词表，不接受动作、效果或环境条件。

结果只证明导入声明支持条件，`visualVerified/humanLabels/qualityGate=null`；本地请求数0不等于来源费用0，来源费用保持unknown。旧动作搜索、篮子、benchmark和既有候选报告不读取本库，旧`independentStaticClothingIndex=false`仍描述原候选匹配报告。详见[使用指南](../references/static-observation-guide.md)与[设计](../design-docs/static-observation-index-spec.md)。

## 协作与正式验证

沿用同目录workspace `f4395711-a8fb-49a3-ad95-7305ce9ea1e8`，新task `gamingcreator-static-observations-20261023`／session `codex-35d31548-8d46-4f1b-b8dc-1886e7f8f355`。Luna/high定位、Astra/low一次复杂设计及唯一Sol/high评估，型号从runtime metadata核实；DSH唯一写八份源码／测试，Codex合同、实跑、公共记录与Git。

三个distinct请求均已结束：初实现`cc01f7cc-7a81-43a5-8a74-ae42355d96bf`，边界追修`8a5c31e4-9e5c-42ff-9c32-055fb153461f`，测试夹具修正`f22a78d1-ace9-4d50-9949-0dde0220fb8b`。恢复／超时只观察原请求，无重投。

独立评估在交付前发现并关闭三项：遗漏SQLite `-journal`链接检查、同part冲突跨来源group绕过、查询组名被错误当作来源组匹配键。初次正式实跑199通过／3失败／1跳过；失败是JSON传str、列表误索引和费用夹具begin带usage，均只修测试，不放宽生产守卫，原失败证据保留。

最终rev4合同`dfc21b73d68027cd5c394413972fac34a576b006507e067816ea45c4334196ac`：

| 检查 | 实际结果 | run ID |
| --- | --- | --- |
| 静态入口及既有CLI／动作／匹配／架构回归 | 203项，202通过／1跳过，零失败／错误，10.41秒 | `9fc62033-5679-434d-9f8b-8f12e11db2c4` |
| 八文件Ruff／格式、六源码mypy | 全部退出0 | `60d43c9a-8f95-4a8c-832b-007c72fff2ae` |
| 原模型／领域／存储／依赖／标注等保护文件 | 12份SHA全部不变 | 主控与唯一评估独立核对 |

真实SQLite无事件Completed、生产CLI子进程导入、另一进程查询和重复复用实际通过；并发、冲突、回滚、损坏、源身份／时钟、V6单帧动作拒绝、旧DB／费用保持实际覆盖。journal硬链接用例在合成受害文件上执行并核字节不变；唯一skip为本机无符号链接权限，不能称全部链接均实测。未修改系统权限。

两回执在文档／Git变化前通过receipt CLI重读，`valid/evidenceComplete/passed=true`，执行前后摘要一致：`ef718a42d1918268637c6b5d5f371884e86f87f00f426d99563126ea2aac462d`。runner为command，pytest依据stdout／JUnit；不声称原生收集证明或整仓verify／wheel。正式进程使用独立pycache前缀与`-B`，无依赖安装、模型下载或真实录像调用。

证据在ignored `artifacts/dsh-static-observations-20261023/`：合同、prompt、完整答复路径、初次／最终JUnit、原始日志、回执、protected-before、validated-source及publication。合入后为历史证据，新里程碑另建Git基线，不修改旧账本重基。

DSH用量单列：3逻辑send、239可见样本，未缓存输入345350／缓存读118510336／输出298503 tokens，缺失／不一致计数0；不是提供方账单、提供方请求数或费用硬上限，与录像API费用分开。

## 已向用户说明与下一步

现在静态声明有独立保存和检索闭环，旧记录与动作保护保持。F006/F009/F010仍false，长钟馗269成功窗／3缺口、469观察、旧费用及原12条标注与纠正未动。无真实用户素材新增静态覆盖，无需重标。

用户补充的三个游戏共6个MP4已完成可用路径登记，见[素材清单](material-availability-2026-10-24.md)；只盘点目录，不代填来源独立性、人工参考或费用许可。下一设计静态观察自动生成的独立Provider／费用／恢复边界，形成有限合同后继续DSH；真实发图仍须具体提案，不因离线开发或素材可用推定获准。
