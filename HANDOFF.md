# 当前接手：四平台预览包已交，继续逐镜头变速

2026-10-31用户确认额度恢复，Goal active，封面文案与四平台预览包已交，继续逐镜头变速。上轮用户额度暂停已结束，项目未完成；全部51项路线accelerated-product-roadmap.md和ADR-003继续生效。

- 最新交付：2026-10-31四平台预览包已交，Goal active：可编辑配置→真实横竖视频/封面→七文件ZIP→本地限值报告；47主树联合测试、补充3换行/版本回归、8源码mypy/Ruff与Sol/high关键评估PASS。实际四平台ZIP/35帧30fps/音轨/旧配置/刷新0POST/新实例0worker通过；故意1字节上限fail、另实测test_only音乐blocked。P034–P037未开始→部分，51项10/19/22≈38%、首产品0/12/10≈27%；人工必做0项/未来8项、技术债10/2/5不变，规则/权利/质量仍未知，无新模型/外部发布。下一逐镜头变速及音频字幕跟随。 证据.cache/platform-main.xml、platform-package-real-browser.json、platform-package-test-music.json、platform-package-mobile.png；合同sprint-platform-packages.md。
- 前批交付：2026-10-31封面文案切片已交，Goal active：已完成成片选输出帧→真实PNG→编辑标题/简介/Tags→保存独立版本/五文件下载；60定向测试、5源码mypy/Ruff及Sol/high关键评估PASS。真实两版第6/34帧RGB逐像素一致，旧版/视频SHA不变，刷新0POST、新实例0worker；修复真实剪辑成片校验异步嵌套与未改含逗号tag被拆分。P031未开始→部分，51项10/15/26≈34%、首产品0/9/13≈20%；人工必做0项/未来8、技术债10/2/5不变。下一四平台配置与七文件发布包/Preflight，无新模型费用。 证据.cache/publication-main.xml、publication-assets-real-browser.json、publication-assets-mobile.png；合同sprint-publication-assets.md。
- 已能用：工作台填写需求→三模板方案/草稿/缺口→选择→真实MP4预览下载；镜头入出点/换序/删除、不可变版本、祖先撤销与重渲染；已有语音/手写字幕、改词/关闭/恢复及SRT/真实中文烧录；新增本地音乐登记、选择、原声/配乐音量、duck/移除/继承及真实混音。
- 本批验证：40通过/1既有Windows symlink权限skip（.cache/audio-main.xml）+49界面/版本通过（audio-ui-main2.xml），7源码mypy/Ruff、唯一Sol/high关键评估PASS；临时收据rename发布增量9通过/同1skip。B原渲染/字幕22兼容通过，不重跑旧全量。
- 真实配乐：0.4秒880Hz本地生成test_only音调已CLI登记；页面保存曲目、原声-6dB/配乐-12dB/duck→真实MP4，改字幕继承mix、移除再MP4，祖先恢复音乐/文字；原5POST仅3保存/2渲染，最终只读刷新0POST/新实例0worker。音调不是商用音乐。证据.cache/audio-workspace-real-browser.json、audio-workspace-output-check.json、audio-workspace-mobile.png。原声本来有880Hz，总谱幅度不一定增加；相位复数差0.000441证明新增，原错误临时脚本保留，未重复渲染。
- 额外修复：旧MKV/PCM音频容器时钟不等于解码音频滤镜时钟，原atrim可能只取几毫秒；改为origin+源微秒绝对秒裁切。PCM非零起点有/无配乐及原offset/VFR兼容通过，原源/分析/费用保持。
- 字幕/镜头前批证据：81镜头版本测试、实际3→2镜头35帧→祖先53帧；60字幕文字测试、真实“冲向→奔向”两个MP4/SRT及字形已查看。见sprint-creation-editing.md、sprint-creation-caption-editing.md及各.cache/*real-browser.json。
- 进度：51项10已交付/19部分/22未开始≈38%；首产品22项0/12/10≈27%。P034–P037刚变部分，其余不靠内部子项虚增。真实质量0/8，F006/F009/F010保持false；人工现在必做0/未来8，技术债17项10/2/5。
- 下一直接做：逐镜头0.5x/1x/2x变速、音频/字幕跟随与真实重渲染（Astra/low已开始只读设计）；沿全产品主线。仍需补候选替换、字幕逐词/样式、变速/裁切/转场、AI选曲/节拍、正式SQLite登记、EXE与商业服务；不得因F006人评全局停开发。
- 使用入口：docs/references/creation-guide.md；音乐登记scripts/register-music.ps1，库.cache/workspace/music，test曲trackId d5fc3e28ba22400e972c0a7292e3483a。无任意路径HTTP导入，许可unknown/user_declared/test_only仅声明，真实权利/分发待核。
- 协作：Astra/low设计，三个Sol/medium库/混音/UI实施，Sol/high唯一关键评估；全部写者/评估已结束，无需等待旧任务。工作树music-library/audio-mix-render/audio-mix-workspace保留备份。临时测试服务关闭，不停止用户原服务。原9个未跟踪.codex/agents文件不改不加。
- 环境：Windows PowerShell，先scripts/env.ps1，主Python -B/共享venv只读，独立worktree指定自己PYTHONPATH/cache，不uv写主venv、不默认GBK读文本。固定FFmpeg生产pin不换。新费用/真实外部发布/组件分发仅限制相应操作，旧许可不重用。

本批合同sprint-creation-audio-mix.md；已确认上批5efef4e推送，本次源码/文档同提交后普通推送并核远端。复工先读本文件/看板第6节，直接继续已授权本地开发，不要求补片/分组/重标或重复旧全量。
