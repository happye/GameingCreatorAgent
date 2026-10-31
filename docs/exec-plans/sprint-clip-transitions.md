# R2-G：交叉淡化转场与变速共存

2026-10-31，Astra/low已只读完成方案，父持久化；变速已提交eb6addf并推送，以下是下一切片，不计功能通过。2026-10-31用户额度不足10%要求暂时收尾，该暂停已于用户恢复额度后结束，当前三Sol分工实施；下述暂停记录为历史检查点。当前Sol子审查触发usage_limit，已披露由Astra完成变速最终增量复核；转场实现可由主控推进，不重复尝试已知额度限制，不因单模型额度停止整个Goal。

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

## 本次恢复执行

2026-10-31用户恢复额度，init CheckOnly与完整环境检查通过；三新独立工作树已应用4文件检查点，按冻结合同并行。core/render/ui由三个Sol/medium拥有，主控公共文档与真实页面；交付后唯一Sol/high关键评估。旧quota错误属上轮，未连续重试。当前功能数字/人工/债务不变，无新Provider/下载/外部发布。

## 交付结果与独立评估

2026-10-31已交付R2-G。三个Sol/medium独立实施核心、renderer/字幕和UI，主控只集成owned文件；唯一Sol/high指定diff与最后刷新增量均限定PASS，无已证实P1/P2。运行时型号见.cache/clip-transition-runtime.json；没有因上轮quota改用未披露型号。

主树49联合测试零失败/错误/跳过（.cache/clip-transition-main.xml），刷新最小修复后8浏览器全部通过（clip-transition-refresh.xml）；6源码mypy/Ruff通过，10文件格式除最后clip_index校验换行外已通过，该1文件格式化后与新增浏览器文件再查通过，语义未变。worker核心118、renderer相关51/最终9、UI7/最终8是分工证据，存在重复，不能相加当唯一覆盖数；未重跑旧全量。

真实UI三版：14788d983ad94ea6b98e0a8b71b00fd2→0e21aa9da8214679ab9d0e0144fb8231，1x/1x、T6、起点0/9、29帧；cd88c91739c54d218942a957091b76d3→97bda0145f9f469999df8f7ef2c4fda5，0.5x/2x、T3、起点0/27、37帧；祖先BASE→c84ad8ec048942c09c88d690a49b9e97→abffa2b218d94874819083d05cb3e49e，cut、起点0/15、35帧。实际字幕[0,.5)与[.3,.966)重叠，PNG已查看两条中文上下可读，BGM继承，旧父文件和原片SHA保持。

29帧成片末帧28生成封面a31a10ad63304e388ffd6890f9022ac0，RGB逐像素一致；B站本地包21cbf11efa614185a4268c409897c8a4为29帧，七文件ZIP/每项SHA通过。test_only音乐资格blocked保持，非商用发布。真实浏览器记录clip-transition-real-browser.json、overlap.png、mobile.png；手机390宽无横溢出，刷新0POST、新服务0worker、pageErrors空。

首次实际QA在全部6个保存/渲染成功后，刷新等待编辑区超过30秒；根因旧projectChanged先await整份历史catalog（逐任务核验），并非成片丢失。最小改为独立启动history后恢复selected job，保留epoch/view；新增悬挂history仍恢复fade8/可render/0POST测试，Sol/high增量PASS。followup复用原6job只新建封面/包2POST，总8POST，没有重渲染。未优化backend catalog，本轮只解决恢复依赖；所有临时服务关闭，无新增技术债项/新Provider/下载/外部发布。

普通短字幕分层实证通过；长文任意多行尚未全面核验，不能承诺绝不相撞，SRT排版由播放器决定。源范围、旧v1/v2、祖先、未知费用、人评保持。P028/P029/P032仍部分，51项10/19/22≈38%、首产品27%不虚增；人工现在0/未来8、债务10/2/5。已向用户说明本批可用与验证边界，下一R2-H候选替换不等人评。
