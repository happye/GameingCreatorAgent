# R2-C：本地音乐登记、版本化配乐与真实混音

2026-10-30，Astra/low只读设计由主控持久化。先落地手动选曲/音量/原声压低配乐，不冒称总方案§31的AI情绪/节拍匹配完成；用户当前必做0项，无新模型/下载/外部发布。

## 音乐与混音合同

- 本地CLI register-music显式选择文件、标题、来源说明及可选许可材料；复制到.cache/workspace/music独占随机trackId目录，最后发布回执，音乐/附件各绑SHA和大小，原文件不动。普通本地可解码音频，拒网络/播放列表/链接逃逸和超限文件，固定FFmpeg探测/解码，导入前后核原SHA。
- track登记包含title/sourceDescription/mediaSha256/durationUs/trackReceiptSha256/licenseStatus，许可状态仅unknown/user_declared/test_only；不提供伪verified。BPM/mood/高潮点默认未知。声明/附件不等于真实权利已核实；本地可预览，未来正式包检查权利，test_only不得正式分发。
- HTTP仅GET /api/creation/music列登记曲目及问题，不暴露原路径/许可原文，不增加任意路径HTTP导入。无曲目时说明本地登记方法，不催用户现在补曲。
- revision可选audioMix完整替换快照：`{bgm:null|{trackId,trackReceiptSha256,gainDb},sourceGainDb,ducking:"off"|"source-v1"}`。省略继承，默认null/0/off，bgm:null明确移除。增益有限-60..0dB，拒bool/NaN/Infinity。换镜头/字幕不丢配置，撤销恢复祖先，旧字段缺省/旧文件字节保持。
- 根源音轨继续原source-clock裁剪/无声补齐；配乐只在最终输出时钟混入，不每镜头重启。48kHz双声道，音乐短循环/长截断；首版从曲首开始。音量、可选source-v1 sidechain、amix normalize=0、限幅及延迟补偿策略明确记录；duck只响应原声能量，不声称区分人声/音效。
- 音乐文件/回执身份在执行前后验证并保护输出路径；缺失/错配失败，不偷偷忽略。完成回执含audioMix、trackreceipt/mediaSHA、权利声明与mixPolicy，失败/取消无completed、不自动重跑。

## 边界接口与分工

先A：Sol/medium独立music-library树，domain/creation_audio.py、infrastructure/music_library.py、cli/music.py、main.py登记参数及相关tests。冻结AudioMix/BgmSelection/MusicTrack及MusicLibrary接口后，再让B/C并行；不是唯一写者，保留他人，不递归。

B：独立audio-mix-render树，ffmpeg_render.py及真实音频tests；复用A域类型，末尾可选audio_mix/music入参，原无配乐路径保持。C：独立audio-mix-workspace树，creation_jobs/revision_jobs/server/static及版本/HTTP/浏览器tests，复用A接口，不改B renderer。主控集成/公共文档/真实工作台，唯一Sol/high审音乐身份/来源/不可变版本与收据。

## 量化验收

测试音调明确test_only：440Hz原声+880Hz音乐有声成片两频均存在；无声素材只有880Hz。未触发限幅窗，音乐-6dB对0dB解码RMS为-6±0.5dB；duck活动窗BGM降≥6dB，释放后恢复基线±1dB。短循环、长截断各真实验证；视频帧准，音频有效时长误差≤1 AAC帧，原声脉冲相对现有基线偏差≤1 AAC帧。源视频/音乐SHA保持，重排/字幕/重启继承、移除与撤销生效，未知曲目/损坏收据/越界路径拒绝。针对性测试，不重跑旧全量。

本地登记和真实混音/工作台使用全部走通后P030才计部分；曲目真实授权、AI选曲/节拍匹配、响度质量/商业权利仍待核。不把测试音调当可商业分发音乐库。

## 本轮交付和收尾

已实现本地登记CLI/PowerShell、不可变音乐库、只读曲库接口、工作台选曲/双音量/duck/移除、修订继承和实际混音。三个Sol/medium分别拥有A/B/C，Astra/low设计，唯一Sol/high关键评估PASS；最终临时收据写完检查取消再rename发布增量也通过核对。主控集成40测试通过/1既有Windows symlink权限skip（.cache/audio-main.xml）、49界面/版本联合通过（.cache/audio-ui-main2.xml）、7源码mypy/Ruff通过；库发布增量9测试通过/同1权限skip。B原22渲染/字幕兼容通过，不重跑旧全量。

真实定量测试覆盖440/880Hz有声/无声、短循环/长裁切、-6dB增益、duck至少降6dB/释放恢复、有效时长≤1 AAC帧和源SHA保持。另修复旧MKV/PCM原声只保留数毫秒的裁切问题：不再把容器time_base当音频滤镜time_base，改按原origin+源微秒绝对秒裁切；PCM非零起点有/无配乐及原offset/VFR兼容通过。

实际CLI登记0.4秒880Hz本地生成test_only音调；页面选择该曲、原声-6dB/配乐-12dB/duck保存并生成视频，改字幕后配乐继承，移除再生成无音乐视频，祖先可恢复配乐及新字幕。原5POST均为显式3次保存/2次渲染；后续只读检查刷新0POST/新服务实例0worker、窄屏无溢出、曲目/产物SHA正确。原片也有880Hz能量，临时脚本错误假定总幅度必须上升；实际相位可抵消，已只读比较两成片880Hz复数分量，差0.000441，未重渲染。记录.cache/audio-workspace-real-browser.json、audio-workspace-output-check.json、audio-workspace-mobile.png。

P030由未开始→部分：全部51项10已交付/14部分/27未开始≈33%；首产品22项0/8/14≈18%。原F006/F009/F010、人评0/8、人工当前0/未来8、技术债10/2/5保持。测试音调不是商用曲库，AI选曲/节拍匹配/真实授权仍未知。

用户提醒额度不足10%，本批保存后暂停新开发，所有写者/评估结束，临时测试服务关闭，不停止用户原服务。下一复工做封面/标题/简介/Tags、平台配置与发布包，沿总51路线；保留候选替换/裁切变速转场/正式SQLite/EXE等未完项，不靠重复旧测试代替功能。
