# Studio 同一发布版本的多平台包

2026-11-07，R2/P035后续切片。四平台独立真实包后端已存在，Studio目前只能单选平台、显示一个结果。本批补一稿多平台批量操作；不冒充P035的全部智能时长/Hook/CTA变体，不自动发布。

## 决策与归属

Astra/low只读设计选择“发布版本级任务投影+Studio串行提交”，不增加持久batch manifest。已有status/request足以恢复已提交任务，UI尚未提交部分不假称持久队列。parent持合同/文档/root集成，Sol/medium在`.worktrees/j1-selected-ranges`分支`codex/studio-multi-platform-20261107`唯一实施，Sol/high multi_platform_guard唯一审身份/幂等/套餐边界。原树旧工作已完整stash保留。

## 接口与行为

- `GET /api/creation/jobs/{publicationId}/packages?projectId=…`核父项目、publication种类和completed状态。按项目/kind/parent筛选原状态后读匹配request，核publicationJobId，返回每次尝试的jobId、平台/profile摘要、父回执摘要、状态/时间/错误。不能受项目catalog最近100条截断；不hash所有完成视频。匹配未终结任务沿既有get恢复中断；列表无新任务/转码/费用，详情/下载仍走原完整核验。
- 已保存且未修改的发布版本可多选平台，点击后固定project/pub/receipt/profile快照，按显示顺序逐项submit→settle；当前项终结再提交下一项。尚未提交/运行/成功/失败/权限拒绝分别显示，各成功包保留独立ZIP、视频及本地检查/水印/发布资格。
- 刷新只恢复服务器已有任务，不自动补提剩余平台。相同profile成功/运行中默认跳过；单项失败/中断显式重试才生成新意图。保留全部旧尝试，不覆盖失败历史。仅本页批次串行，不声称跨标签全局转码互斥。
- 原API intent允许可选作用域，以项目/pub/receipt/profile隔离；网络结果不明保留requestId并先查列表，不能直接发新请求复制包。已确认失败/中断后用户重试才清该scope意图，不能影响其他平台或既有单任务调用。
- show/保存/提交/轮询/详情及catch/finally都核当前项目/打开版本代次；切换后停止旧批次继续提交，已接受任务继续运行且不污染新页面。
- 每次submit仍过原OS锁/幂等/check_entitlement。Free按同render跨发布版本累计平台，其他平台拒绝如实逐项显示，不能自动切套餐/跳过限制。不改账本/费用/权利声明，不触发真实平台发布。

## 归属文件与验收

实施文件：ui/creation_jobs.py、ui/server.py、static/studio/publish.js、api.js及新相关HTTP/browser测试；必要小样式另说明。复用package_jobs既有真实转码/七文件/ZIP，不再造导出器。

实际另获parent授权最小修改main.js：open携来源project，works绑定项目，切换时清旧open，防新catalog到达后重新消费旧项目发布版本；Edit/Publish共用入口只接收匹配项目状态。

真实浏览器从同一render保存一次pub并选两个平台：依次执行，下载两个实际ZIP，每包恰为video.mp4、cover.png、title.txt、description.txt、tags.json、platform.json、validation.json。核profile/同pub文字封面/视频可解码/检查与水印。使用测试隔离允许套餐，不改用户套餐。

刷新第一项运行中→恢复同jobId且不提交第二项；切project/pub+旧响应延迟不串；超过100条历史仍找旧包；Free首平台成功、另一平台拒绝且同render新pub不能规避；故意一包转码失败不影响成功包下载、显式重试新jobId且旧尝试可追溯；丢首次响应重提同意图只有一个jobId。无外部云/付费/Release操作，真人观感仍未验收。

## 独立树证据与闭环

最终`.cache/multi-intent-final.xml`：14通过/0跳过，40.855秒；此前原真实包/HTTP相关12通过，组间有重叠不累加。真实同pub双ZIP核七文件集合、title及视频解码，profile/其余文字封面/水印等沿原package完整校验链，并非本批逐项独立像素断言。105条后续历史仍找回旧包，完成列表不读MP4；Free同pub及同render新pub均不能规避第二平台限制。

唯一Sol/high发现并闭环3项P2：旧失败行重复新意图、恢复运行A时直接提交B、切project后旧open回流。另补预注册未知窗口：真实submit已接但阻塞写status前、两次连接结果丢失/GET仅旧失败、刷新第三次POST，requestId始终相同，释放后只一个新增完成job/ZIP。scoped package发送前保存会话请求身份，unknown不清，只有该意图绑定任务确认终结才能清；存储不可用则提交前明确拒绝。旧响应不能覆写新key/id，默认unscoped行为保持。真实main切project及8种迟到成功/错误含catch/finally/旧批次后续提交均覆盖，专项最终通过。root完整集成门禁仍待执行，不提升P035整体交付或真人质量。

root组合字幕预览/旧字幕/多平台/旧发布/运行时及health合同：47通过/0跳过、117.140秒（`.cache/r2-caption-packages-root.xml`）。源码自动合并，仅API文档末尾新增段落冲突，已保留两组完整合同。随后跑`.cache/r2-caption-packages-full-verify.log`完整门禁；通过前main保持b4023c4。

最终`.cache/r2-audio-worklet-full-verify.log`：5035通过/7跳过、1723.43秒，格式/Ruff/mypy209源/CLI全部通过。早期mypy重名及PCM采集失败日志保留；别名已修，AudioWorklet采集/异常清理已通过9项定向及唯一复核，不更改生产混音或阈值。本批技术集成完成，P035整体和真人质量保持partial/未验。
