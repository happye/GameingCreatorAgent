# 特殊源时钟自动映射交付

2026-10-24，Phase 0／F007验收工具。新准备的原片参考页和候选评审页，能在实际核对浏览器时钟后处理已验证的非零PTS、音视频不同起点MP4。用户可直接按当前位置登记规范源时间、播放同一规范区间并在区间末暂停，省去自行加减偏移。已有页面包、原标注和评分规则保持原身份。

## 实际验证

- 正式核心回归 **256 passed／0 skipped，129.777秒**，含真实FFmpeg／probe／Chromium两页面、条码画面与帧PTS独立对照、纯转换／JS一致性、下载再验证、原评审／参考／架构与区间HTTP回归。JUnit在ignored artifacts/dsh-source-clock-mapping-20261024/tests-core-r6.xml；不是整仓测试或真人准确率证据。
- 九Python文件Ruff／格式、五源码scoped mypy、三JavaScript语法检查通过。
- 实际原 references-v2 标注页面包与已保存修订记录，经生产CLI重新读入到新输出目录成功。10个已接受事件、context原字节、record-input原字节和导出plan值均保留；原12记录及纠正不改。37历史保护文件、922原项目文件SHA不变。
- 同一Sol/high独立审阅R1–R8 PASS。只对变更分支复核，没有由评估者重复全套。

最终合同v6 `1155ea481af6e9e3507250ddb5b56c8a6b660d87b7ef485dadd4fd512b3c7311`，以下三组回执在本次公共文档及Git变化前逐一复核：

| 正式case | runId | 结果 |
| --- | --- | --- |
| source-clock-quality | 3ea636d1-1160-4cdf-8911-1f6aad648ebf | valid／evidenceComplete／passed |
| source-clock-existing-reference | 1ea70b14-b505-4ec9-8fc8-a6ba8588e6b8 | valid／evidenceComplete／passed |
| source-clock-direct | 7aae003a-80e1-4244-8373-dea824ff8a6c | valid／evidenceComplete／passed |

12源码／测试原始SHA及规范Git blob已冻结，正式执行前后相同；最终提交再核对blob。回执捕获原stdout/stderr及执行、源、完整声明运行依赖指纹；command runner本身不证明pytest收集完整，主控另核JUnit非空、无失败／跳过。最终文档与Git保存之后不把旧sourceFingerprint称为当前完整树有效。

## 工作台扩展回归的已知失败

广回归275项273通过／2失败（137.239秒）。登记输出成功后替换status.json遇WinError5，残留状态变interrupted，会阻断该工作台步骤；HTTP参考导入CLI成功但返回缺busy的确切原因仍未证明。ui/benchmark_workflow.py本轮未改，不能称两故障已修或都属于同一竞态。原失败JUnit／stdout及guard计划保留；本次独立页面映射与生产CLI旧包复用通过，工作台整流程未通过。TD012新增复现，继续使用受影响工作台步骤前优先处理。

最终运行清单仅排除已证在测试中被Chrome改写的debug.log输出，其他运行依赖保留；完整init通过，无工具链pyc漂移，另显式设置PYTHONDONTWRITEBYTECODE保护子进程。唯一窄复查两旧失败仅作probe，结果另存，不当根因已修证据。

## 支持范围与保护

实测范围为项目本地Chromium与合成MP4：正常零起点、整体非零PTS、音频晚于视频，以及视频晚起的有效画面范围；另含重封装负偏移与分片MP4实验。其他浏览器、编码和任意实际素材兼容性未泛化通过。

共用纯转换为 `sourceUs = floor(playerSeconds × 1000000 + 0.5) − originUs`，反向为 `(sourceUs + originUs) / 1000000`；仅在实际媒体轴、有限时长、已知流范围和容差匹配后启用。不能用seekable宽度猜偏移。视频尚未出现的区间不能自动取时或回看；额外未选长音轨造成时长矛盾等情况继续手填与本机原片核对。

播放器加载代次、URL、查询或时长变化会使旧映射失效；定位超时不把已赋currentTime当完成。两页拒绝异常增长、非有限时长、迟到事件；仅已实证且有上界的非零PTS定位时长增长可接受。参考页重验恢复旧位置前及等待后均核token／代次／URL。正常同代次恢复仍可用，受控迟到seeked反例证明重载后不写旧位置。

runtimeClocks只作新页面运行投影，排除在旧参考身份hash之外，但有投影时仍严格重建核验。旧context字段形状与automaticTimeCapture语义保留。旧不可变页面包不重写，不要求重标；旧特殊时钟包继续原手动行为。

## 协作、失败与恢复

原生task `gamingcreator-source-clock-mapping-20261024`／session `codex-94269cc4-7c00-4bbe-917e-bdd6205a1a9f`，四个工程请求均COMPLETED，完整终态报告分别按request/hash读一次。最后请求93834a15-12a1-416e-bd2b-949ecb88439b，resultSHA9c5fb3b4584ea83f7cabc038861c17a0d8c6d6dacf3ec064d6d4faad8cc2f95f。当前无watcher、无产品源码写者；不得重投这四轮。

首轮独评发现旧参考身份、定位超时假成功及可见播放器有效态问题；同DSH集中追修后通过。第三轮新增位置恢复分支的一处异步保护由第四轮精确修复。初轮失败、编码修复及开发探针原日志保留，不伪装一次成功。

Codex曾未及时取回已完成报告、沿用旧RUNNING；恢复后补读终态并纠正为单watcher增量观察。主控额度用尽期间DSH报告可由原会话恢复取回，不保证主控停顿期间自动验收或派下一轮。

正式v2初次run在启动前因Codex将27个ignored只读条目加入继承baseline的合同而被scope门拒绝，无测试启动或UNKNOWN执行。隔离工具分支修复51f42dd（30通过／1 Windows文件软链接权限skip、原合同22回归、同Sol/high PASS）提供显式补充入口；仅补27项，原654基线条目／root／HEAD／index逐值保留，旧资产不改。一次补充后回原configured CLI正常修订／执行，主工具安装fc47d97未改。

旧包正式验证首轮失败是Codex把imported-v1导出结果误作原编辑包；生产入口正确拒绝。原脚本和失败回执保留，v5新增独立测试脚本改用原references-v2，产品源码不变，静态检查因合同／测试输入变更有理由重验，扩展组275项为273通过／2失败，且因误收Chrome生成debug.log导致指纹变化，该回执不能作为最终有效验收。原failed计划和日志保留；同一独评确认不阻断独立TD006页面，只另跑聚焦核心guard，排除已证生成日志而完整保留执行文件／库／配置。

## 费用、质量与下一步

本切片没有新录像／图像API请求，不重跑旧付费任务。DSH工程模型用量另存，不能宣称免费或视为提供方完整账单。原28.5秒单帧唯一调用估算¥0.001492、未知旧账及一次许可耗尽状态保持；不得借¥0.50余额加发。

阶段仅读取一次原生usage：本task单一原生session为complete、450个末次采样，未关联／缺失／矛盾为0；非缓存输入891,744、缓存读183,635,840、输出495,132 tokens。此为DSH会话投影，不是双方总账或供应商账单，工程人民币费用未知；完整coverage与字段记录保留在usage-final.json，不重复加总流式中间样本。

F006／F009／F010仍false，人工判断不自动填写。原269成功／3缺口／469观察不变且非Completed。只读来源对齐已证明：10个人工正例只对应钟馗failed run，32已有排名均异源，暂不能进行有效同源Completed覆盖投影。下一回原Phase 0来源独立性、事前参考与固定Top10真实质量路径；复用已有标注和六新增素材，仅实际触发原人工或新费用依赖时提醒，不重复催同待办。
