# Phase 0 长录像预处理与持久化

2026-10-07，root / Codex，codex/visual-details，接94d5f29，顺序开发；旧worker／worktree冻结。上一轮为实际进展：长事件语义检索已交付并验证；本轮继续长录像主线，不恢复TD010微修。

## 主要交付及归属

F002／F004／TD001：FFmpeg双音频时间日志受16MiB整段缓冲限制，长录像预处理可失败。以有界逐行读取向映射解析器传递已识别时间记录，未识别诊断仍限流，保留源PTS、音频分段映射、首尾裁切与完成manifest发布边界。Windows Job取消／超时／进程树回收与普通Provider输出限流保持原合同。

root独占infrastructure/media_process.py、ffmpeg_media.py、新流式时间日志行为测试、test_media_process.py及必要test_media_integration.py适配；scripts/test-media.ps1／validate-media.py提供显式采样／帧数／期限选项，并验证真实本地入口。相关媒体规格／特性证据／公共交接串行更新。不改Application分析费用／续跑合同，不新增模型调用。

## 验证路径

逐行解析与既有解析结果一致，包括VFR／非零或负PTS／音频gap与overlap／裁切；管道拆行／EOF尾行、有界长行和未识别诊断、解析失败／取消／超时终止回收。真实项目内FFmpeg处理合成一小时低分辨率带音轨视频，验证超过旧日志容量后仍能生成完整证据，保存media阶段并由第二进程重新读取。该合成录像不证明实际游戏理解、小时级真实游戏编码性能或独立人评。一次完整verify，在实际实现后执行；无变化不重复检查。

状态：流式管道与映射解析已实现，41定向／0fail／0error／0skip（12.728s）；真实PowerShell 7离线入口、中文路径与显式采样／帧数／期限另项通过。Windows PowerShell 5宿主工具命令兼容记录TD011后停止调查，不影响主线。原F006/F009/F010未验收状态、未知费用及新调用授权边界保持。

## 一小时实际媒体工具与持久化证据

ignored artifacts/long-media-validation/check-hour-media.py／hour-report.json：真实FFmpeg生成一小时32×32／1FPS视频及48kHz音轨，视频源起点5秒、音频异步起点；源12,031,447bytes／SHA8836bbf97a0b221fa9deb3840cdd5e416c52d944a061b277599030093942fc89。旧无consumer音频日志读法实触media.output_limit；新预处理13715ms，3600图／源0–3599秒，音频57,600,341样本／168,752分段／起点78ms／尾3600.099313秒，声明duration3600.099334秒，0间断／0裁尾样本。约63,231,864bytes已识别音频时间记录逐行消费，只保留1578bytes未识别诊断；图片记录1,011,282bytes，余诊断423,001bytes，单行／未知输出限制保持。

media阶段保存11725ms，另一进程通过真实SqliteTimelineStore只读重建、manifest／source／audio身份及全部映射摘要一致；run仍running，只有media完成，没有ASR／视觉调用／人评。当前验证进程峰值working set235,360,256bytes（约224.5MiB），不包括FFmpeg子进程峰值；原开发DB SHA保持，预算／付费调用未触及。已向用户通俗汇报一小时本地处理／保存／恢复、实际14秒／12秒与低分辨率合成的范围。真实游戏小时性能／模型理解及F006仍待验证。

完整verify已通过：1912passed／1 Windows文件symlink权限skip，331.50s；140格式文件／72类型文件、lint／CLI／双离线wheel通过。SHA8f2507f3ed38c36764834af51f9470abadbcc12a18b7593c28f95383c4b520a7，71包文件逐字节同源码，不含缓存／素材／DB；JUnit1913／0fail／0error／1skip。回执.cache/long-media-targeted.xml（41）、entry.xml（1）、tests.xml／verify.log／package.json；此后文档变化不重复完整检查。旧Windows PowerShell 5缺工具命令的失败和错误测试来源断言见ERR-018／TD011，现有PowerShell 7入口真实通过。

下一主线提供独立的离线素材准备步骤：先抽帧／提音轨／保存media阶段及原分析配置，随后显式执行分析时从已完成阶段继续，避免准备素材就要求API凭据或开始付费。接现有run_new_analysis／resume_analysis与原费用／来源身份，先登记新范围及验收，不回到TD010微修。当前新付费试验仍待授权，不使用旧已执行授权或更换目录清除旧unknown。用户已获一小时处理效果和下一具体动作汇报；本次仅保存本地，发布以publication回执为准。
