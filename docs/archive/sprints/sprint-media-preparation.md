# Phase 0 独立离线素材准备

2026-10-07，root / Codex，codex/visual-details，接c2b4f14，顺序开发，旧worker与worktree冻结。

## 主要交付与归属

F002／F003／F004：提供prepare-media命令，离线抽帧／提音轨，保存原配置、后续分析费用上限与media阶段；任务等待显式analyze --resume。准备不构造ASR／视觉Provider、HTTP传输或费用账本，不读取API密钥；配置中的费用上限不是本次调用或新增费用授权。

root拥有application/analysis.py与storage.py、cli/main.py、infrastructure/sqlite_store.py、独立准备／续跑行为测试与必要媒体入口集成测试、公共交接和使用文档。复用原抽帧宽度／源时钟／pipeline身份；media完成后存为pending，不伪造完整分析。离线续准备只接受没有ASR／视觉工作或调用的任务；显式分析继续保留原配置／预算／未知费用检查。

## 验收与下一步

验证准备不触及模型／网络、保存与第二进程重读、显式分析跳过已完成media、历史图像宽度身份、失败／取消的media恢复、来源变化和已分析任务拒绝、上传重复帧的覆盖上限提示。用实际本地FFmpeg及无密钥入口处理合成素材；准备完成不代表理解或检索验收，F006/F009/F010保持false。完成相关测试和一次完整verify，之后不重复无变化检查。

当前状态：已交付。18新准备行为覆盖等待状态／原配置、完整性拒绝、取消与失败恢复、不降回模型任务、原512／1280抽帧身份、重叠上传帧计数和显式分析跳过media；另9新CLI拒绝与3真实媒体入口／另一进程／覆盖不足。最近65定向passed（20.53s），更早95passed／5错误测试预期，已直接纠正，失败回执保留；一次完整1942passed／1 Windows文件symlink权限skip，301.42s，141格式／72类型／lint／CLI／双离线wheel通过。SHA10497aac761d0a919546998f2168e6a28aaf7eae2e7376a1379c3b10b6ea9a45，71包文件同源码且不含素材／缓存／DB；JUnit1943／0fail／0error／1权限skip。回执.cache/media-preparation-final-targeted.xml／tests.xml／verify.log／package.json；之后仅文档／ignored证据，不重复完整检查。

ignored artifacts/media-preparation-validation/check-offline-hour.py／hour-report.json：真实新CLI处理上一小时合成源，32761ms准备／保存，run26a49c8e606446c5a2e971bf1bb9724f为pending，3600图／900窗口／4499含重叠上传帧，57,600,341音频样本／168,752分段，原非零时钟和音轨SHA保持。禁构造ASR／视觉／传输／预算账本、删除当前进程密钥后实际入口通过；续准备禁止preprocess再次运行仍成功，25067ms核对原文件／重建，另一独立进程摘要完全一致，配置hash不变，media attempt1、0invocations，未生成完成时间线。原开发DB SHA保持，0新调用／预留／人评。该正数¥5只是保存的后续上限，不是费用授权或实际预留；没有执行输出的分析命令，显式分析跳过media用替身测试验证，真实一小时ASR／视觉未执行。

已向用户汇报素材准备／显式分析分开、实际小视频和一小时33秒／重复核对25秒及合成范围。重复核对耗时归入已有TD005资源／source I/O后续事项，暂不优化，TD010／TD011延期。下一主线提供素材任务清单与阶段／原配置／费用状态查看，帮助找回准备和未完成任务并选择显式续跑；先登记归属，费用未知和来源完整性保持。上一交付c2b4f14普通push一次网络速度超时失败（.cache/long-media-publication.json）；继续本地，不循环重试，不改main或全局网络配置。
