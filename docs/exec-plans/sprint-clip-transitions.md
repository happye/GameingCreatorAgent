# R2-G：交叉淡化转场与变速共存

2026-10-31，Astra/low已只读完成方案，父持久化；变速已提交eb6addf并推送，以下是下一切片，不计功能通过。2026-10-31用户额度不足10%要求暂时收尾，当前暂停于下述检查点。当前Sol子审查触发usage_limit，已披露由Astra完成变速最终增量复核；转场实现可由主控推进，不重复尝试已知额度限制，不因单模型额度停止整个Goal。

## 冻结合同

新增edit-decision-revision-v3，每镜头v2字段增加transitionIn={type:'cut'|'crossfade',frames:int}。第一镜头cut/0，其他cut也0，crossfade正整数；旧v1/v2只在内存解释为全cut，旧字节/SHA不改。源区间、speed、clipId、根保护和父链保持。换序/删除新形成的连接在UI重置cut，用户重选，不偷偷迁移转场。

设镜头输出N_i、入场重叠T_i，S_0=0，S_i=S_(i-1)+N_(i-1)-T_i，总frames=sum(N)-sum(T)。每镜头T_i+T_(i+1)<N_i，至少一帧独占且禁止三重重叠。RenderPlan统一提供start_frames/frames，默认全cut；渲染、字幕和收据不各自重算。

字幕用S_i/fps+(sourceUs-startUs)/1000000/speed；手写覆盖[S_i/fps,(S_i+N_i)/fps)。SRT保留按起止稳定排序的真实重叠cue，不合并虚构句子；ASS重叠段以稳定不同垂直通道避免挡字，其余恢复底部。可扩仅排版用clip/channel身份，不靠同文字猜来源，SRT播放器排版未知说明边界。

## 真实合成

继续先产已变速/统一尺寸fps的无损NUT。全cut保留当前显式duration concat快路径。有淡化时逐连接双输入无损合成，避免Windows长命令：cut串接，crossfade用xfade(duration=T/fps,offset=当前累计frames/fps-T/fps)，原声acrossfade同overlap和固定线性曲线。统一time_base/零PTS/48000样本率；每连接后视频精确累计帧、音频绝对累计sample边界整理，避免毫秒舍入漂移。最后再烧字幕/BGM/duck/编码MP4，BGM从缩短后的总时间0起播。

固定FFmpeg xfade/acrossfade和像素格式需实际工具验证，不凭字符串测试假报；私有任务临时文件，失败不发布receipt，不改原片/证据。父源范围不可扩大，错误S_i/伪速度/非法重叠拒绝。

## 实施与验收

合同核心：rendering/creation_editing/revision_jobs及测试，负责v3严格重建/共享帧布局；合成字幕：ffmpeg_render/creation_subtitles/cue排版类型及真实媒体测试；页面：每连接cut/crossfade帧数、重叠后总长、换序重置、保存/祖先恢复。文件所有权先明确，不在独立工作树间覆盖他人；主控统一文档/看板。

实测30fps红/蓝各30frames，6frame淡化后54frames，第二镜头S=24：过渡前纯红、中段混色、之后纯蓝（有损颜色用容差）。三镜头混合0.5/2x，边界/总帧精确；原声两频过渡共存及前后单频、样本总长；ASR/手写重叠烧录可读；BGM/duck、无音轨、v1/v2回读/祖先、下游末帧封面与包通过。0新产品Provider/外部发布/下载，不重跑无关全量，P028/P032仍部分。

## 2026-10-31 暂停与可恢复检查点

直接原因是用户明确要求因额度暂时收尾；无新的产品阻断、人工操作或费用请求。转场尚不能使用，不代表整个项目受阻或已经完成。已交付源码基线eb6addf，主树两文件临时改动已在备份核对后恢复；旧9个未跟踪角色文件未改未加入。

持久补丁：`docs/exec-plans/checkpoints/clip-transitions-20261031.patch`（12816 bytes，SHA256 `5ad22cb9d851e65394cf1923b6a8e84ca927d7e1bf7a86871054e97d77a33e18`）。保存4文件：application/rendering.py、creation_editing.py、creation_subtitles.py及domain/creation_subtitles.py。完整文件备份与逐文件SHA另存`.cache/clip-transition-wrapup/`；原字幕工作树`.cache/worktrees/clip-transition-render`保留，不能把其中旧依赖覆盖回主树。

- 已编写但未独立评估：v3 transitionIn严格字段、帧重叠约束、共享start_frames和父链重建；已有镜头/变速核心67项兼容测试及两源码mypy通过，但尚无新增转场测试。这些结果不能证明转场完成。
- 字幕worker仅完成使用共享输出起点、cue clip_index身份和稳定排序，未测试；ASS重叠排版、SRT重新量化后身份保留未完成。
- FFmpeg合成器、前端控件、浏览器和真实媒体验证均未完成；没有新的转场MP4或成功收据。
- 已核补丁可应用到主树基线：`git apply --check docs/exec-plans/checkpoints/clip-transitions-20261031.patch`。主树无转场运行时代码变更，无须重复旧全量测试。

复工顺序（不重开架构分析）：

1. 读HANDOFF/看板第6节后，在基于当前main的独立工作树应用上述补丁；主Python/venv只读，指定本树PYTHONPATH与cache。先添加v3核心行为测试，覆盖54帧/第二镜头24帧、非法重叠/布尔/首镜头淡化、源范围/祖先链/v1-v2兼容。
2. 按本合同实现逐连接双输入xfade/acrossfade，以及字幕量化后的clip身份和ASS重叠排版；每步固定帧/样本边界，全cut保留旧快路径。
3. 页面提供cut/crossfade及帧数，显示真实短后总长；换序/删除仅对新连接重置cut，保存v3并支持祖先恢复。
4. 通过本合同真实红蓝54帧、双频原声、三镜头混合变速、字幕不挡字、BGM/duck与静音；然后真实页面保存→渲染→刷新0POST/新实例0worker→末帧封面/发布包。唯一关键边界独立评估后才集成并计交付，勿重复旧全量。

真实UI可复用2镜头基线`be9753d88b3a42a6affa926c5e495afa`：15+20帧，第二镜头入场6帧应总29帧/第二起点9帧；祖先恢复35帧。test_only音乐只供本地验证，不改权利结论。speed真实证据见sprint-clip-speed.md与.cache/clip-speed-*.json；原7014a5fc56f04e84901150c973c947a5失败现场保留，不重跑旧失败任务。

用户已获说明：变速已可用；转场只是设计/部分代码，下轮直接补合成、字幕、界面和真实验证，再做候选替换。51项10/19/22≈38%、首产品27%不虚增，人工现在0项/未来8，技术债17项10/2/5；本次0新产品Provider请求、0下载、0外部发布。
