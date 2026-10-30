# R2-D：真实封面与可编辑文案

2026-10-31恢复开发。Astra/low publication_assets_design已核P031及下述合同，无路线阻断；保留总51项/ADR-003，不等F006人评、不发模型请求。

用户流程：打开已完成MP4→选输出帧→编辑标题/简介/Tags→保存新版本→预览真实PNG、下载五类文件。render的默认文案为本地可编辑模板，不能称AI生成或平台已审核；每次保存独占新publication job，旧render/旧文案不覆盖。后续另接四平台配置和七文件发布包，此批不冒称发布包完成。

接口：POST /api/creation/publications exact `{requestId,renderJobId,expectedRenderReceiptSha256,coverFrame,title,description,tags}`；GET /api/creation/jobs/<render-or-publication>/publication只读返回renderJobId/父收据SHA、文案、coverFrame、frames/fps/width/height/videoUrl与明确模板/草稿状态。kind=publication，parentJobId=renderJobId。coverFrame严格整数排除bool，0≤frame<frames，FFmpeg固定pin按输出帧select解码PNG，不换源时钟、不重新渲染视频。

输出cover.png、title.txt、description.txt、tags.json、publication.json，最后原子完成receipt绑定五SHA、job/request、render收据/MP4 SHA与帧。下载固定allowlist路径 /api/creation/jobs/<publication>/publication-files/<name>，复用safe/MediaResource；GET/HEAD和刷新不执行新任务。title1–200/description≤5000/Tags≤20每条1–50为本地约束，拒控制字符，不当平台官方限制。

归属：Sol/medium publication-assets-backend树拥有新核心/提帧/任务helper、creation_jobs/server及后端tests；Sol/medium publication-assets-frontend树拥有creation静态文件、browser及旧mock兼容。不是唯一写者，保留他人、不递归。主控公共文档/集成/真实浏览器，唯一Sol/high关键评估负责文件/父身份/恢复。后端publication独立execute/verify分支，禁止误从直接父render.request取runIds；预期父SHA从内部验证收据获取，不依赖剥离SHA的public get。

验收：真实首/末帧提取PNG可解码且尺寸正确；浏览器填中文/选择帧/下载及保存第二版本，旧版本不变；新服务回读/刷新0POST；同requestId复用、不同内容冲突；越界/bool/任意路径及父或输出篡改拒绝；中断不自动重做。只做必要定向及实际产物检查，原质量/费用/素材/音乐权利保持。只有公开真实流程通过后P031计部分，当前数字不变。

## 已交付与验证

2026-10-31封面文案切片已交，Goal active：已完成成片选输出帧→真实PNG→编辑标题/简介/Tags→保存独立版本/五文件下载；60定向测试、5源码mypy/Ruff及Sol/high关键评估PASS。真实两版第6/34帧RGB逐像素一致，旧版/视频SHA不变，刷新0POST、新实例0worker；修复真实剪辑成片校验异步嵌套与未改含逗号tag被拆分。P031未开始→部分，51项10/15/26≈34%、首产品0/9/13≈20%；人工必做0项/未来8、技术债10/2/5不变。下一四平台配置与七文件发布包/Preflight，无新模型费用。

架构Astra/low、两Sol/medium实现、Sol/high唯一关键评估，型号/推理由实际运行元数据核对（.cache/publication-assets-runtime.json）。主树60测试通过（publication-main.xml）、5源码mypy/Ruff通过；真实现有MP4两版frame6/34封面RGB与原帧逐字节一致，五文件/旧版/刷新/新实例均验证，PNG/手机截图已看。记录.cache/publication-assets-real-browser.json。初次实际剪辑成片因async save内调用父验证的asyncio.run失败，现两处校验to_thread+回归修复；失败任务保留不冒称完成。P3未改Tags含逗号被拆分已按原数组保留修复，2桌面/手机回归通过。临时服务关闭，无原素材/成片写入，0新render/模型/下载。
