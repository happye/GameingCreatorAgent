# 当前接手：按额度提醒暂时暂停，下次直接续转场

2026-10-31：按用户“额度不足10%，暂时收尾”指令暂停开发，项目未完成。逐镜头变速已交付并推送eb6addf；转场只有设计/部分代码，已保存可恢复补丁，未集成主线、未计为交付。全51项10已交付/19部分/22未开始≈38%，首产品22项0/12/10≈27%；当前必须人工0项，未来待办8项，技术债17项10/2/5不变。复工先续转场合成/字幕/UI，再候选替换；不等F006人评、不重复旧全量。

## 已能使用与证据

- 工作台需求→三模板方案/草稿/缺口→真实MP4预览下载；镜头裁短/换序/删除、不可变版本与祖先恢复；手写/改词/关闭/恢复字幕、SRT与中文烧录；本地曲库、双音量、duck、混音继承/移除。
- 2026-10-31封面文案：成片选帧PNG、标题/简介/Tags版本与五文件下载。60定向测试、5源码mypy/Ruff、Sol/high关键评估PASS；真实第6/34帧RGB一致，旧视频SHA不变、刷新0POST/新实例0worker。合同sprint-publication-assets.md。
- 四平台本地预览包：可编辑preset→横竖视频/封面→七文件ZIP/Preflight。47联合+3增量，8源码mypy/Ruff、Sol/high PASS；四平台实际35帧/音轨/ZIP通过。规则仍为本地preset、权利/真人质量未知，test_only音乐会blocked。合同sprint-platform-packages.md。
- 最近已交付逐镜头0.5x/1x/2x：源范围不变、保音高原声/字幕跟随、BGM输出时钟、祖先恢复；138主树联合+19最终渲染增量、5源码mypy/Ruff通过。真实40→17→祖先35帧，SRT1.000/.233/.500秒；新40帧成片末帧封面和包通过，刷新0POST/新实例0worker。
- 变速评估：Sol/high初审发现补尾P2已修后触发额度限制；已向用户披露Astra/low完成最后两处增量的限定静态PASS，不冒称Sol复核或任意音频瞬态样本级对齐。证据.cache/clip-speed-main.xml、clip-speed-real-browser.json、clip-speed-downstream.json、clip-speed-mobile.png；最终19项在clip-speed-render树.cache/speed-concat-final.xml。已交付源码eb6addf已推送并核远端。

## 未完成转场检查点：先读这里再动手

架构师Astra/low方案已冻结在[转场合同](docs/exec-plans/sprint-clip-transitions.md)，不必重新设计。合成worker只交了未测试字幕基础，未交FFmpeg合成；主控核心亦未完成新增行为验证，不计交付。所有写者已结束，无需等待旧任务。

4文件未完成代码保存为[可恢复补丁](docs/exec-plans/checkpoints/clip-transitions-20261031.patch)，git apply --check通过；主树源码已恢复到已验证eb6addf。补丁SHA256 `5ad22cb9d851e65394cf1923b6a8e84ca927d7e1bf7a86871054e97d77a33e18`，完整文件/SHA备份.cache/clip-transition-wrapup；字幕原树.cache/worktrees/clip-transition-render保留。下次在独立工作树应用补丁，勿直接把旧worker依赖覆盖主树。

复工顺序：v3核心行为测试→逐连接xfade/acrossfade真实合成→重叠字幕ASS排版/身份→页面cut/crossfade帧数/保存/祖先→真实媒体和浏览器→唯一关键边界评估→集成。量化完成标准：30+30帧入场重叠6后54帧、第二起点24；画面混色、原声双频、字幕不挡字、混合变速、BGM/静音、旧版本/祖先与末帧发布包均通过。实际UI基线15+20重叠6应29帧，合同列了jobId。之后候选替换，再沿全51项主线。

## 状态与边界

- 整体51项10已交付/19部分/22未开始≈38%，首产品22项0/12/10≈27%；转场内部代码不增加数字，P028/P029/P032仍部分。质量线真实0/8，F006/F009/F010 false；不因此全局停止创作/桌面/商业化开发。
- 用户现在必须人工操作0项，未来8项按[user-actions](docs/exec-plans/user-actions.md)量化触发；技术债17项10已解决/2部分/5未解决。本次无新产品Provider请求/下载/真实发布，不重新申请已用过的旧许可；未改素材、旧分析、费用、人工记录。
- 暂停直接由用户额度提醒触发，项目未完成。下次用户恢复后续做即可，不要求重新讲历史、补片、分组或重做标注。
- Windows PowerShell，先scripts/env.ps1，主Python -B/共享venv只读；worktree指定自己PYTHONPATH/cache，不uv写主venv、不默认GBK读文本；固定FFmpeg生产pin不换。Sol本轮quota受限已披露，复工按运行时能力选工，不假称执行模型。
- 已有9个未跟踪.codex/agents角色文件原样保留，不加不删。旧工作树与失败现场保留；测试服务均已关闭，不停止用户原服务。正常提交推送，不force。入口docs/references/creation-guide.md；进度看板第6节是唯一下一步入口。
