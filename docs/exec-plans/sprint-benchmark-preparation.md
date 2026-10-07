# Phase 0 独立验收素材登记与查询冻结

2026-10-07，root / Codex，codex/visual-details，接7b5a7b3；旧worker／worktree冻结，顺序开发。上一素材任务清单已提交且实际8任务／工作台验证完成，属于progress。

主要交付归F006：freeze-benchmark先读取人工填写的素材／原录制组／开发测试分区／是否看过结果／查询族／查询及人工参考计划，本地probe／hash原视频，在新目录保存不可覆盖的原输入、规范计划和来源身份／冻结时间／准备缺口；不抽帧、不分析或收费。bind-benchmark把指定分区的冻结来源绑定到同项目已完成run，核对原SHA／时长／完整性，生成现有benchmark v1清单及来源回执。候选评分始终空，缺参考／独立性／样本量显示尚未准备；本轮不代替人工填写真实标签或宣布F006通过。

root独占新application/benchmark_preparation.py、infrastructure/benchmark_preparation_files.py、CLI组合入口、新计划模板／PowerShell入口／行为及真实小媒体与已有开发素材验证、相关手册／合同和公共记录。现有benchmark计分／十固定槽／70%门槛与检索、SQLite、费用／来源身份不改。

验证严格字段／重复／类型、原录制和内容／查询族跨集泄漏、人工参考组／主少例负例门槛、草稿不能产生确认人评、来源hash／时长绑定和新目录不覆盖、冻结内容篡改／源变化拒绝，绑定不调用搜索／模型／预算。实际本机开发录像保存／绑定仅作流程证据，不做独立样本或标签。必要定向后一次完整verify；非阻断小问题直接记录后继续主线。

已向用户说明先冻结原素材／查询，再绑定分析结果的使用效果；正式验收仍需独立人评。新¥4.07授权未答、旧¥4.065536未知预留保留；0新上传／请求／预算，本轮不循环联网。

## 完成交付与验证

已实现benchmark-plan-v1纯Application：严格字段／重复／类型／参考范围，登记原录制组、分区与是否看过结果、查询族；复用原benchmark人评／微秒合同。freeze-benchmark只probe／hash，核对原输入与原源未改变、新目录独占保存plan-input.json／freeze.json，UTC时间、SHA回执最后发布。bind-benchmark只读Completed来源／完整性、冻结SHA与时长，指定分区完整映射，转换旧benchmark v1、候选标签空、草稿／独立不足保持false。绑定目录不写入项目或原冻结资料。旧检索／数据库／费用合同不变。

追加benchmark --binding，打开store／加载embedding前核对原绑定，仅candidateLabels与humanLabels.reviewed可变；查询／参考区间与组／来源／版本／填写人／原确认与独立性变更拒绝。原manifest无参数维持旧行为；正式冻结流程用新参数。准备ready只表示资料检查，原录制与人评声明未认证，qualityGate始终null。

47新行为、扩展133定向passed，2.07s。首轮测试helper引用猜错两次已直接改为现有test_detail_query.snapshot；119passed／2 fixture断言错误（空返回在已确认参考下应判失败、重复创建media目录）直接按原合同修正，2项复核0.51s。完整verify2034passed／1 Windows文件symlink权限skip，287.17s，结果时间和环境见.cache/benchmark-preparation-tests.xml／verify.log；148格式／75类型／lint／CLI及双离线wheel SHAa27ca9c94bcebb1aa3aafc4991842e6cd644409b43c837f7358fca3135ba9260通过。74包文件同源码，不含媒体／缓存／DB；JUnit2035／0fail／0error／1权限skip，.cache/benchmark-preparation-package.json。之后仅文档／ignored证据，不重复完整检查。

实际三开发素材54.743220／64.943220／95.175874秒：来源均已Completed／已看模型结果，两个Atom保守同录制组；冻结1516ms／只读绑定487ms／另一进程读回相同SHA和3素材／3查询、human确认false／independentfalse／候选评分空。PowerShell7中文计划文件Freeze与另次Action Bind入口均真实通过，Bind1209ms，manifest及来源字节同直接CLI。832项目文件及3原视频字节保持，0Provider／普通搜索／预算／新真实人评。首轮wrapper把env.ps1误放根目录，直接纠正scripts/env.ps1，不改全局环境；该修正只涉及不在Python打包／完整检查范围的脚本，由实际两动作核验，不重跑完整。原失败回执.cache/benchmark-preparation-real-first.log保留。

ignored artifacts/benchmark-preparation-validation/check-preparation.py／report.json／script-bind-report.json／计划.json／runs.json与frozen／bound／bound-script为本机证据，不随Git传输。准备只有两已知录制组、无独立主查询／人评，不能当F006样本。旧漫画unknown¥4.065536／无nextCommand、新proposalSHA06829ab9dc835545ef8c4de5c829351fc686ce70c990d8c902b9b919b2f062c6保持，.cache/benchmark-preparation-invariants.json。F006/F009/F010false，旧worker冻结。

## 已汇报与下一交付

已向用户通俗说明先冻结／后绑定的作用、防止同源与事后换查询、草稿保持未验证、实际三开发录像／1.5秒与0.5秒／字节和费用保持。详见[交付汇报](report-2026-10-07-benchmark-preparation.md)。下一root主线候选人工判分入口：固定十位、原区间回看、人工0–3及独立事件映射、保留冻结依据并导出评测文件；先登记归属，不造真实评分，不用开发PV宣布独立通过。TD005／TD010／TD011继续延期，工作台本轮无静态／服务合同变更无需重启。

本轮0push／远端读取，网络上次超时后不循环；本地HEAD及.cache/benchmark-preparation-publication.json为准，普通授权分支待补推，不更新main／强推。Goal active，上一交付和本轮都是progress。
