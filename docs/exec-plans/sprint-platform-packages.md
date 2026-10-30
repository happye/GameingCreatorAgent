# R2-E：配置驱动四平台变体与七文件预览包

2026-10-31，Astra/low publication_assets_design核方案；复用P031/db8dc35，不停在文案五文件。每平台独立package任务，实际横竖编码、封面变换、七文件和ZIP，不发模型/发布请求，不改变原成片或源时钟。P034–P037交付前仍未开始，不因合同增加进度。

## 冻结接口

GET /api/creation/platform-profiles返回四份本地可编辑preset。POST /api/creation/packages exact `{requestId,publicationJobId,expectedPublicationReceiptSha256,profile}`。GET /api/creation/jobs/<id>/package返回profile快照、实测输出、validation和下载链接。每job只一个平台，四平台各提交一次；预期publication收据SHA从验证后的内部记录提供（publication GET快照需额外公开自身publicationJobId/publicationReceiptSha256供调用）。

profile exact `{Platform,RuleVersion,UpdatedAt,Source,Fields}`，Source=`{kind:'local_preset',label:'用户可编辑本地导出配置，非官方规则'}`。Fields=`{video:{width,height,fit:'pad'|'crop',codec:'h264',pixelFormat:'yuv420p'},cover:{width,height,fit:'pad'|'crop'},limits:{maxBytes:null|int,minDurationMs:null|int,maxDurationMs:null|int,titleMaxChars:null|int,descriptionMaxChars:null|int,tagMaxCount:null|int,requiredTags:string[]}}`。帧率/总帧数继承父成片，不自动改Hook/CTA/时长；尺寸限制是本地导出选择，不冒称官方规则。

## 产物与真实性

七文件video.mp4、cover.png、title.txt、description.txt、tags.json、platform.json、validation.json；ZIP只含七文件，不含源视频/源路径/许可附件/内部报告。receipt放ZIP外，绑定七文件、ZIP、配置canonical SHA、publication/render父身份和文件SHA，最后原子发布。父验证在异步编码中通过to_thread等合适边界，避免复现nested asyncio。

视频真实scale+pad/crop→H264/yuv420p，音频保留已混音内容（可AAC copy），封面由已存PNG变换。实测probe/解码核尺寸、codec、fps、帧数/时长/字节数及文本/Tags。编码失败不登记completed；仅超本地限值仍保存报告便于修改。

状态分开：generationStatus=completed代表七文件/ZIP可用；localChecks=pass|fail比较实际产物和所选本地配置；未配置限值not_configured、未知规则unknown，不能算pass。publicationEligibility=unverified|blocked：官方规则/素材权利/真人质量未知保持unverified；test_only音乐blocked，user_declared不冒充核权利。此批不产生可商用发布资格。

官方检索不足以取得四平台完整当前规则。设计师仅找到快手https://www.kuaishou.com/help/feedback/4000?categoryId=hot上传流程、小红书https://school.xiaohongshu.com/helper/detail/1390?jumpFrom=www部分能力，不能推导通用规则；B站旧文/抖音证据不足，登录后限制未知。以local_preset继续实现，不伪官方profile。

## 归属和验收

后端Sol/medium独立platform-package-backend：profile域、validation纯逻辑、FFmpeg/ZIP、package_jobs、creation_jobs/server、必要publication snapshot自身身份扩展及后端tests，四preset JSON也归其一人；前端Sol/medium独立platform-package-frontend：creation静态文件和界面tests/mock。不是唯一写者，保留他人、不递归。主控文档/集成/真实四平台文件验证，Sol/high唯一文件/身份/权利/恢复评估。

验收：四平台各真实七文件+ZIP、横竖尺寸/封面/音轨可解码，帧率帧数不变；配置修改新版本/旧版不变；本地超限fail、规则unknown、测试音乐blocked；父/文件/配置篡改拒绝；请求幂等、刷新/新实例0新worker；ZIP无内部路径/源素材/附件。针对性检查，原质量/费用/人工0项保持。

## 已交付与证据

2026-10-31四平台预览包已交，Goal active：可编辑配置→真实横竖视频/封面→七文件ZIP→本地限值报告；47主树联合测试、补充3换行/版本回归、8源码mypy/Ruff与Sol/high关键评估PASS。实际四平台ZIP/35帧30fps/音轨/旧配置/刷新0POST/新实例0worker通过；故意1字节上限fail、另实测test_only音乐blocked。P034–P037未开始→部分，51项10/19/22≈38%、首产品0/12/10≈27%；人工必做0项/未来8项、技术债10/2/5不变，规则/权利/质量仍未知，无新模型/外部发布。下一逐镜头变速及音频字幕跟随。

Astra/low设计，两Sol/medium后端/前端，唯一Sol/high审查PASS。主树47测试通过（.cache/platform-main.xml），Ruff/8源码mypy通过；新增简介CRLF/裸CR/TAB保留支持，read_text归一化曾导致校验失败，已改raw bytes UTF8并3项真实版本/重启回归通过。真实工作台四独立平台任务，横1280x720/竖720x1280/720x960；帧35/fps30音轨正确、ZIP exact7内容SHA与文件一致，无内部路径/原素材/附件。1字节限值报告fail且可下载；旧profile回填/重启不重encode；另真实test_only音乐预览包completed但eligibility blocked，非商业通过。实际证据.cache/platform-package-real-browser.json、platform-package-test-music.json、platform-package-mobile.png，截图已看，临时服务关闭。下一变速，不重做原验证。
