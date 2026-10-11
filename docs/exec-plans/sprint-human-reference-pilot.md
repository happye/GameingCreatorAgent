# 首份真人参考：核对、冻结和小规模分析准备

2026-10-11，Phase 0／F006。用户提交根目录原片标注记录.json，包含钟馗15分钟录像四查询共12个事件，其他两录像暂无区间。用户进一步确认武器只指装备菜单等展示界面，两长剑特写不算；老者逃跑事件理由误复制，明确同意纠正。原文件保留，修订副本记录授权、SHA和每项变化，不改已有references-v2包。

本节点root复用公开参考导入／冻结入口，负责ignored记录、范围说明、分析准备及公共文档；只有真人语义／费用／身份的独立审查需要唯一task_quality_guard，无普通重复review，无新产品源码或完整测试。保存的真人文件加入明确ignore，不提交原始答案、素材或数据库。

测试口径不变：boss战、武器展示界面、释放连招、剧情演示。武器两条特写从修订副本剔除并留排除回执，不因不存在有效标注就宣称该视频没有界面。其他两录像“似乎没有boss／武器”、剧情／战斗内容声明保留原语气，不将空参考或普通战斗当确定负例／连招。

当前可用三查询为boss1／连招5／剧情4，共10个已标注样例，各查询已标数不足10，使用现有sparse结构运行有限对照。用户说“登记了一些真实事件”，未确认穷尽覆盖：实际全片事件数及全片Recall未知，sparse不代表该片真实仅有这些事件。从经过原包验证的修订计划派生单来源、三sparse查询的新试验计划，披露暂未纳入的武器及其他8项，原12查询资料保留。冻结保存真实源SHA、时长与准备缺口；不通过完整代表集／主查询或70%gate，F006/F009/F010false。

顺序：保存原字节和用户纠正回执→公开入口验证原参考包与三源，导入修订副本→派生并冻结小规模计划→独立身份／语义／费用边界检查→准备具体付费分析提案。未取得新费用与发送授权时不调用模型；既有三pending任务的每任务5元参数不等于授权，旧v5两次许可已耗尽。确认费用方案后才分析、Completed绑定和固定候选真人评审；原片答案不能在看结果后补成事前标签。

恢复先查本轮操作回执，所有输出用新目录，completed步骤不重跑；root只负责自己的新增文件并保留他人工作树。关键节点同步HANDOFF、assignments、progress、phase计划和human-inputs，给用户通俗汇报材料够做小对照、为何不算正式通过、下一实际动作。

## 已完成／验证证据

ignored artifacts/human-reference-pilot-20261011保存human-record-original、human-record-corrected-v1及input-provenance；原SHA dcf1b689c2ea保持。原参考包context SHA4eb42ab580f6及文件原字节保持，修订记录仅两排除、一理由及labelVersion后缀变化。公开prepare-benchmark-references导入2.16秒exit0，仍12查询；imported-v1/receipt保存输入SHA97f5c6338e00及导入计划SHA3bf315aa53e4。

从已验证计划保留三查询原文字／事件ID／分组／区间／理由，只改变试验集合及kind；scope-provenance保留被省略九查询原因。公开prepare-benchmark冻结1.50秒exit0；冻结SHA8cc6fffcc8693d93ca850a9d35a188b01ef5d7f38d6822cc5f73eeea5a8556b4，单来源／保守组，blockers仍representative_recordings_below_ten与test_main_query_missing，qualityGate=null。原完整12项计划不覆盖。

唯一human_reference_execution_guard完成有界只读关键审查，最终PASS、无阻断问题，root持久化evaluation-final.json；指派原生task_quality_guard，但本轮没有另取得型号执行元数据，不声称实际型号已认证。root final-readback-v2单独绑定当前提案和limitations SHA，10执行文件、媒体源、原人工记录、当前参考包及保存配置匹配，SQLite字节不变／pending／调用、事件、转录0。先前v1完整媒体读回1903图／272请求体只作对应历史证据，不能单独证明v2当前提案。

budget-boundary-readback为纯内存账本：两次未知各保留2.032768，占4.065536，下一预留被拒；不是实际花费、执行或全片估价。无产品源码改动，不加镜像测试、不重跑完整验证或真实准备。通俗结论已汇报并同步[本轮报告](report-2026-10-11-human-reference-pilot.md)与公共进度。

## 新分析提案／下一步

当前提案analysis-proposal-v2.json，SHA f608c4dedac69ee261ac56ba110c8446e808bfc533ed26116b568c95fe8c6f6f；limitations SHA2c969173e2c9e8c510c277ad884fc41322d920b0419621623740a14c2ff36891；输入清单SHA7fdb7cb21ba99622a17dc6c9da68b9dfd7cd995d4df806a2394a681418170f64。未交付的v1是描述未知费用立即停止的旧草案，仅保留历史，v2按实际既有策略修正，不改请求和保存配置。

仅长钟馗952.101688秒，source SHA7437abfab778，run5c7894aa10e94b8aa82533bd77f9871e。最高新增¥5，DeepSeek chat/completions／deepseek-flash／phase0-vision-v6提示词SHAa60d114d9dd8。正常272窗口，1903唯一注册图、累计2445帧次；既有可重试失败每窗口最多追加两次，共最多500实际发送尝试、5000累计帧次，全部受同一预算。发送仅图片／源时间／冻结提示词和参数，不发送原片、音轨、ASR文本、查询或真人答案；本机ASR保留本机。官方价目已定点查验，计价是估算而非账单。

保存的¥5上限不可在resume时修改；本预算不能承诺整片完成，可能剩余不足下一次保守预留而提前停止。所有旧unknown及新未知预留保持，不自动增加预算／新建run／人工重复执行。总分析超时3600秒。新费用和发送许可待用户，旧已执行v5许可不覆盖。

获具体授权后另存用户答复与execution-started回执，再核对这份提案和执行身份，仅运行已冻结命令一次。执行结束核对用量／账本／Completed状态；只有Completed才绑定frozen-v1、生成固定检索及真人评审，产生候选就提醒用户。这轮只报告已标样例命中、漏掉及人判可用性；一场boss不能切成多场，覆盖长boss区间也不证明任意短窗口可用。若拿本轮结果调优，再收新的独立验收集，不把事后追加标签改称事前答案。

发布仅本地commit；用户断网，本节点不执行Git网络。最后确认远端f5a3a69，恢复普通push仅codex/visual-details，main及强推不操作。已完成抽帧、导入、冻结及exclusive输出不得重跑。
