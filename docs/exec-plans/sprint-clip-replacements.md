# R2-H：从已选录像中替换镜头

2026-10-31，Astra/low只读完成架构及接口补充，主控冻结此合同。沿全51项加速路线；本文件是实施合同，不计功能交付。转场R2-G先完成独立评估和集成，本切片可在独立工作树准备纯核心。

## 用户得到什么与完成标准

在某镜头选择另一条已保存事件，准确预览原片，确认替换并保存独立版本，再渲染。候选包含根请求明确选中的全部Completed run，即使根成片未使用该run也可以选择；不新增付费分析、不接受客户端路径或伪证据。旧版可以恢复，替换后字幕、配乐、变速和转场继续可编辑。

量化验收：根选A/B但原片只含A，换成B未入片事件后真实视频/原声出现B；同run替换、跨run替换、再裁短/换序/变速/设转场和祖先恢复均走通。旧手写字幕在新画面零残留，未换镜头字幕保留，ASR只用各clip对应run；输出帧布局一致，误差≤1帧。两侧连接重置cut，其他连接不变；末帧封面与发布包通过。原根/修订/MP4 SHA不变；范围外/非Completed/伪event或evidence/路径/过期父收据/篡改清单和源SHA均拒绝。失败不登记完成；刷新0POST、新实例0worker、新Provider请求0。

## 冻结架构

旧v1–v3及根精确校验保持严格。新增独立v4重建分支，不放宽旧“只能裁短父镜头”以容纳未知clip。根候选范围取已验证根请求runIds，不从当前EDL猜来源。

`creation-candidates-v1`包含rootReceiptSha256、projectId、allowedRunIds、runFingerprints={runId:fingerprint}及candidates。每候选含candidateId、run/event/media身份、sourceSha256/sourcePath/sourceDurationUs、startUs/endUs、evidenceIds、scriptDraft及uncertainty。candidateId绑定root、run fingerprint、eventId。公开响应去sourcePath，服务端完整清单保留路径；客户端仅引用身份。

timelineFingerprint固定投影（纯函数不读文件、不包含invocation/费用/ledger）：run_id、status、config_hash、configuration中实际存在的pipeline_version/pipeline_hash；asset身份、源路径/SHA/duration/probe_version/origin_seconds及streams(index/kind/time_base/start_pts/duration_ts)；events全部字段；evidence全部字段；transcripts媒体/源区间/文字/uncertainty。实施前按实际类型确认字段，不虚构属性。规范UTF-8 JSON sort_keys=True/separators=(逗号,冒号)/ensure_ascii=False；Fraction为[分子,分母]、SourceRange为[start,end,duration]，SourceInstant有类型标签；events/evidence按ID排序且重复拒绝，stream按index，transcripts按规范字节排序但保留重复；事实/标签/证据数组原顺序。源文件实际hash验证留给I/O层。

候选GET确定性生成清单和SHA，不为浏览创建新任务。首次替换提交重新生成并比较SHA，再将完整清单放入新修订收据；后代携同样清单并复核所有run fingerprint。清单SHA统一使用规范JSON内容摘要；收据另外绑定实际文件字节SHA，不能混用。

## v4请求和重建

沿现有revision基本字段，增加candidateManifestSha256和replacements。clips仍是父clipId无重复有序子集；每行沿v3精确字段clipId/startUs/endUs/speed/transitionIn，transitionIn沿用type键。replacements为[{targetClipId,candidateId}]，target须唯一且在clips中恰好一次。

替换占位行的startUs/endUs指候选内的源区间，speed必须1x。默认取候选事件内不超过旧镜头输出时长的一段，按帧量化并显示真实变化。未换行继续只能在父源区间内裁短。服务端从候选构建全新行，不复制旧源身份；新clipId=SHA256(canonical([replacement-v1,rootSHA,parentSHA,targetClipId,candidateId,startUs,endUs]))，并保存replacesClipId。EDL保存replacements映射target/candidate/newClipId。新镜头及下一镜头入场规范化cut；其他连接保留。客户端保存后拿到新身份，再编辑新字幕/转场。

v4后代即使replacements=[]仍使用v4，禁止降级；祖先恢复仍从被选祖先开新分支。旧target字幕从最终ID集合移除；新镜头默认自身run已有ASR，缺失为空。请求不能借旧target把旧覆盖塞入新画面；未换字幕和全片AudioMix按既有规则继承。

新增纯Application接口：timeline_fingerprint(timeline)、build_candidate_manifest(root_receipt_sha,project_id,allowed_run_ids,timelines)、candidate_manifest_sha(manifest)、build_revision_v4(parent_edl,root_receipt_sha,parent_receipt_sha,clips,replacements,manifest)，以及严格重建/源绑定后返回RenderPlan的验证入口。调用方先验证根/旧祖先，再逐代重建v4；未知clip不能流入旧validate_revision。

## 持久化、预览与所有权

新creation-revision-receipt-v2固定revision.json/edit-decision.json/candidates.json三文件；旧receipt-v1双文件检查原样。revision.json保存原请求、清单摘要和父/root绑定，回读从请求重建EDL完整比较。v4每代携相同候选内容；UI层复核根run范围/Completed/fingerprint/实际源SHA。预览仅接job/manifest/candidate身份，复用已验证媒体Range，不接受任意路径。保存失败不改父，完成回执最后发布；刷新/重启仅回读。

工单：纯核心creation_replacements.py及新核心测试先独立实施；之后revision_jobs/creation_jobs持久链与server预览接口一位owner，creation.js候选选择/预览/替换一位owner。主控统一文档/集成/真实验证；唯一Sol/high评估数据/身份/持久化边界，不叠普通review。所有写者独立工作树、主venv只读，保护他人和旧9个角色文件。

当前人工必做0项，未来8项、技术债17项10/2/5不变；不因原F006人评停止本功能实现。部分模板/已有片段支持不等于全产品质量和商用资格通过。

稳定实现接口：allowed_run_ids为list[str]；validate_revision_v4(parent_edl,revision_edl,root_receipt_sha,parent_receipt_sha,clips,replacements,manifest,timelines)->RenderPlan，调用者先验证根/祖先及根run范围，再逐代验证。公开候选额外含sourceClock（runtime_clock_document原格式）及previewUrl，预览用共享浏览器源时钟模块测量并换算，不能盲用currentTime。候选视频端点固定candidate-video及planId/candidateManifestSha256/candidateId三参数。

## 实际交付与评估（2026-10-31）

R2-H已交。Sol/medium三独立树完成纯核心/持久链HTTP/前端，主控集成；Sol/high对核心/后端及前端分段限定PASS。最后真实发现ASSETS未注册共享clock，主控补入口与HTTP脚本加载回归；候选标签改录像名/源秒数/描述，内部ID仍只作身份value。后续Sol额度受限已向用户披露，最后静态资源/标签/有界超时增量由Astra/low worker只读限定PASS，不冒称Sol或真实媒体评估通过。

主树92联合零失败/错误/skip（.cache/clip-replacement-main.xml），资源修复后3 HTTP/前端（clip-replacement-asset.xml），共享clock65项（clip-replacement-clock.xml，包括延迟3.3s事件默认拒绝/10s成功/20ms拒绝与非法参数、既有未完成定位仍拒绝）。分组存在重复，不能简单相加成独立覆盖数。5源码mypy/Ruff、9文件格式通过；clock suite仅cacheprovider WinError5警告，测试全过，未重跑旧全量。

真实双run根0bb52d27ede743528bdee06cb8217ee4的request选漫画f76...和Atom96...，其chronological EDL实际仅含Atom三镜头；基线v3 73531d5cf59c4c1898cbab3e9b491b81仅用Atom、手写文字和test_only BGM。GET有151候选，其中可选漫画事件证明不只当前入片来源。跨run保存fd110a75f7c74952a8f7ce3413b50881→7fd72648a439403491a0499440152295，6帧；在同新ID裁短/0.5x/淡化后eb09dc8f632d437abe2544b73d5fc9da→99ab7f9e8b6d49fabb9eb58a25116a71，5帧；同run再换96c1fc97867c4529b65f1779db82a01d，再换序08aa12e7e57c424fa823cae72825cf35→3bc1cd44baa7460bbac4487437e3971e，6帧；祖先分支4f3185c3f9e4436c9a28883723f437c2→9de5956ea2c34edc81ebebfcd2bc56ff，5帧。均3fps、有音轨、BGM继承；新画面旧手写0残留，未换字幕保留，祖先原文字恢复。跨run帧截图已查看确为漫画画面；两源实际无ASR，跨run ASR绑定由行为测试覆盖，未伪造真实语音。

跨run成片末帧5封面6c6f87edb31d4304b0f3ee66f3a4c685与原输出RGB逐像素一致；发布包b15c176cd10f46e981d2ddbdfdc623de仍6帧/3fps，七文件ZIP/逐项SHA通过，test_only资格blocked。实际浏览器11 POST=5保存/4渲染/封面/包，刷新0POST、新实例0worker、pageErrors空；原根/旧修订/原片SHA保持，390宽无横溢出。证据.cache/clip-replacement-real-browser.json、clip-replacement-cross-run.png、clip-replacement-mobile.png。

第一次预览缺资源入口（尚无替换/渲染任务）已修；其后HTTP全部206且header时长正确，但旧3秒定位超时导致seek_incomplete，保护合理，未当成功。主控继续完成保存/渲染时如实保留unsupported；追加seekTimeoutMs有界参数仅creation显式10秒，旧验收页面仍缺省3秒、seeked/解码就绪/原时钟判定不变。最后仅只读重测同漫画候选：59.262929秒、duration95.175873、readyState4、0POST/pageErrors空，clip-replacement-preview-verified.json。未重渲染四份成片。原未通过预览记录保留（诊断含NaN），最终严格JSON clip-replacement-delivery.json用null呈现旧缺值并另附最终验证，不覆盖历史或假改旧结果。

P027/P032保持部分，51项10/19/22≈38%、首产品27%；人工0必做/未来8、债务10/2/5不变，0新Provider/下载/外部发布。下一R2-I本地旁白，资产纯模块已备但未接完整流程，尚不计新功能通过。
