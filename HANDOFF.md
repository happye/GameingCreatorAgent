# 当前接手：转场已交，继续候选替换

2026-10-31交叉淡化已交付，Goal active：工作台逐连接直接切换/淡化帧数、v3版本与祖先恢复、真实画面/原声淡化和重叠字幕，混合变速/BGM同步。主树49联合+刷新修复后8浏览器、6源码mypy/Ruff通过；唯一Sol/high核心与刷新增量PASS。真实UI29→37→祖先35帧，29帧末帧28封面RGB一致/七文件包通过，刷新0POST/新实例0worker、旧文件/原片SHA不变。51项仍10/19/22≈38%，首产品27%；人工现在0/未来8、技术债10/2/5不变。下一R2-H候选替换，Astra合同已冻结，纯核心已备，正在接持久链/页面；未计替换交付。

## 已能使用与证据

- 工作台需求→三模板方案/草稿/缺口→真实MP4预览下载；镜头裁短/换序/删除、不可变版本与祖先恢复；手写/改词/关闭/恢复字幕、SRT与中文烧录；本地曲库、双音量、duck、混音继承/移除。
- 2026-10-31封面文案：成片选帧PNG、标题/简介/Tags版本与五文件下载。60定向测试、5源码mypy/Ruff、Sol/high关键评估PASS；真实第6/34帧RGB一致，旧视频SHA不变、刷新0POST/新实例0worker。合同sprint-publication-assets.md。
- 四平台本地预览包：可编辑preset→横竖视频/封面→七文件ZIP/Preflight。47联合+3增量，8源码mypy/Ruff、Sol/high PASS；四平台实际35帧/音轨/ZIP通过。规则仍为本地preset、权利/真人质量未知，test_only音乐会blocked。合同sprint-platform-packages.md。
- 最近已交付逐镜头0.5x/1x/2x：源范围不变、保音高原声/字幕跟随、BGM输出时钟、祖先恢复；138主树联合+19最终渲染增量、5源码mypy/Ruff通过。真实40→17→祖先35帧，SRT1.000/.233/.500秒；新40帧成片末帧封面和包通过，刷新0POST/新实例0worker。
- 变速评估：Sol/high初审发现补尾P2已修后触发额度限制；已向用户披露Astra/low完成最后两处增量的限定静态PASS，不冒称Sol复核或任意音频瞬态样本级对齐。证据.cache/clip-speed-main.xml、clip-speed-real-browser.json、clip-speed-downstream.json、clip-speed-mobile.png；最终19项在clip-speed-render树.cache/speed-concat-final.xml。已交付源码eb6addf已推送并核远端。

## 最近交付与当前下一步

转场已完成[合同](docs/exec-plans/sprint-clip-transitions.md)及真实UI29/37/35帧与下游末帧封面/包验证；证据.cache/clip-transition-main.xml、clip-transition-refresh.xml、clip-transition-real-browser.json、clip-transition-overlap.png、clip-transition-mobile.png。先前未完成补丁保留为历史，禁止重新应用覆盖当前实现。首次QA只在刷新恢复超30秒处停止，已生成6job完整；修复历史列表阻挡后复用它们续测，未重复渲染。普通短字幕已查看，任意长文排版不保证；SRT播放器自行决定重叠布局。

下一项是[R2-H候选替换合同](docs/exec-plans/sprint-clip-replacements.md)，Astra/low架构和接口补充已冻结。纯核心在.cache/worktrees/replacement-core，27新增/此前93联合PASS，尚未集成或计交付；持久链/HTTP由Sol/medium在replacement-backend实施。新v4和候选清单独立验证，根/旧v1-v3不可放宽；候选来自根选全部Completed run，换后新clipId、旧手写字幕移除、两侧转场cut、AudioMix继承、跨run ASR准确绑定。页面接入与真实跨run出片/重启/祖先/末帧包还需完成，之后唯一关键评估。

已交付转场/变速源码在主树，新replacement core/backend尚在独立树；不要复制worker非owned旧依赖覆盖主树。所有已结束转场worker可复用，型号按运行时元数据核验。复工先看看板第6节，直接续已有授权开发，不重开转场架构/旧全量，不要求重讲历史或重标。

## 状态与边界

- 整体51项10已交付/19部分/22未开始≈38%，首产品22项0/12/10≈27%；转场属于既有部分功能的内部能力，不增加数字，P028/P029/P032仍部分。质量线真实0/8，F006/F009/F010 false；不因此全局停止创作/桌面/商业化开发。
- 用户现在必须人工操作0项，未来8项按[user-actions](docs/exec-plans/user-actions.md)量化触发；技术债17项10已解决/2部分/5未解决。本次无新产品Provider请求/下载/真实发布，不重新申请已用过的旧许可；未改素材、旧分析、费用、人工记录。
- 旧暂停直接由额度提醒触发；当前已恢复，项目未完成。复工直接续做，不要求重新讲历史、补片、分组或重做标注。
- Windows PowerShell，先scripts/env.ps1，主Python -B/共享venv只读；worktree指定自己PYTHONPATH/cache，不uv写主venv、不默认GBK读文本；固定FFmpeg生产pin不换。Sol本轮quota受限已披露，复工按运行时能力选工，不假称执行模型。
- 已有9个未跟踪.codex/agents角色文件原样保留，不加不删。旧工作树与失败现场保留；测试服务均已关闭，不停止用户原服务。正常提交推送，不force。入口docs/references/creation-guide.md；进度看板第6节是唯一下一步入口。
