# 当前接手：缓存事故已止血，继续本地旁白

2026-10-31缓存事故已止血：精确删除58.29GiB失控测试NUT，实测释放62,589,505,536字节；根因是空音轨变速测试失控写盘、无文件容量门及失败媒体/工作树长期保留。运行期文件/目录/余量限额、原生FFmpeg -fs与退出复核、失败NUT回收、pytest完成回收已落地；58项扩展通过，3个旧mock签名修正后连同新边界12项通过，5源码mypy/Ruff及Astra/low限定静态评估通过。两棵已入库工作副本已释放，其他历史副本待逐项核清；用户明确未手动删除，narration-integration消失仍未归因。51项10/19/22约38%、首产品27%不变，人工现在0/未来8；新增TD018部分，债务18项10已解决/3部分/5未解决。Goal active，随后恢复本地旁白，未提前计P026。

## 已能使用与证据

- 工作台需求→三模板方案/草稿/缺口→真实MP4预览下载；镜头裁短/换序/删除、不可变版本与祖先恢复；手写/改词/关闭/恢复字幕、SRT与中文烧录；本地曲库、双音量、duck、混音继承/移除。
- 2026-10-31封面文案：成片选帧PNG、标题/简介/Tags版本与五文件下载。60定向测试、5源码mypy/Ruff、Sol/high关键评估PASS；真实第6/34帧RGB一致，旧视频SHA不变、刷新0POST/新实例0worker。合同sprint-publication-assets.md。
- 四平台本地预览包：可编辑preset→横竖视频/封面→七文件ZIP/Preflight。47联合+3增量，8源码mypy/Ruff、Sol/high PASS；四平台实际35帧/音轨/ZIP通过。规则仍为本地preset、权利/真人质量未知，test_only音乐会blocked。合同sprint-platform-packages.md。
- 最近已交付逐镜头0.5x/1x/2x：源范围不变、保音高原声/字幕跟随、BGM输出时钟、祖先恢复；138主树联合+19最终渲染增量、5源码mypy/Ruff通过。真实40→17→祖先35帧，SRT1.000/.233/.500秒；新40帧成片末帧封面和包通过，刷新0POST/新实例0worker。
- 变速评估：Sol/high初审发现补尾P2已修后触发额度限制；已向用户披露Astra/low完成最后两处增量的限定静态PASS，不冒称Sol复核或任意音频瞬态样本级对齐。证据.cache/clip-speed-main.xml、clip-speed-real-browser.json、clip-speed-downstream.json、clip-speed-mobile.png；最终19项在clip-speed-render树.cache/speed-concat-final.xml。已交付源码eb6addf已推送并核远端。

## 最近交付与当前下一步

转场已完成[合同](docs/exec-plans/sprint-clip-transitions.md)及真实UI29/37/35帧与下游末帧封面/包验证；证据.cache/clip-transition-main.xml、clip-transition-refresh.xml、clip-transition-real-browser.json、clip-transition-overlap.png、clip-transition-mobile.png。先前未完成补丁保留为历史，禁止重新应用覆盖当前实现。首次QA只在刷新恢复超30秒处停止，已生成6job完整；修复历史列表阻挡后复用它们续测，未重复渲染。普通短字幕已查看，任意长文排版不保证；SRT播放器自行决定重叠布局。

R2-H已按[候选替换合同](docs/exec-plans/sprint-clip-replacements.md)完成：真实双run根只用Atom仍能选漫画候选，四成片6/5/6/5帧及末帧封面/包，旧手写字幕清除/祖先恢复通过。证据.cache/clip-replacement-delivery.json（严格JSON整合原流与最终预览）、clip-replacement-main.xml、asset.xml、clock.xml、preview-verified.json、cross-run.png和mobile.png。旧预览unsupported诊断原样保留；10秒有界定位最后严格通过，不能重新跑四成片补证据。根request仍是唯一候选来源范围，v4独立重建，旧根/v1-v3不放宽。

下一[R2-I本地旁白合同](docs/exec-plans/sprint-local-narration.md)已由Astra/low冻结。narration_assets树四文件完成，13契约/取消/timeout+1中文真实SAPI、2源码mypy/Ruff证据存在；worker交付消息后quota报错，不需等待假运行。模块在.cache/worktrees/local-narration-assets，未接任务/UI/混音。主控新增domain/creation_narration.py草稿未集成使用；narration-mix树仅依赖拷贝、renderer还没实现（worker启动即quota失败）。Sol当前usage_limit已披露，主控继续，必要独立复核明确Astra，不连续重试同一失败。

旁白下一顺序：主树串行恢复并接入已写asset模块/严格选择与长度门→narration job/回读/试听/继承移除→renderer输出帧起点/三路混音与duck→页面生成/挂接/试听→文本和显式新版下游包→真实中文/0与非零起点/超长拒绝/祖先/重启→唯一关键边界评估。源/费用/旧AudioMix语义保持，WAV不得静默截断/循环或变速，未确认商用声音许可。

## 状态与边界

- 整体51项10已交付/19部分/22未开始≈38%，首产品22项0/12/10≈27%；转场属于既有部分功能的内部能力，不增加数字，P028/P029/P032仍部分。质量线真实0/8，F006/F009/F010 false；不因此全局停止创作/桌面/商业化开发。
- 用户现在必须人工操作0项，未来8项按[user-actions](docs/exec-plans/user-actions.md)量化触发；技术债18项10已解决/3部分/5未解决。本次无新产品Provider请求/下载/真实发布，不重新申请已用过的旧许可；未改素材、旧分析、费用、人工记录。
- 旧暂停直接由额度提醒触发；当前已恢复，项目未完成。复工直接续做，不要求重新讲历史、补片、分组或重做标注。
- Windows PowerShell，先scripts/env.ps1，主Python -B/共享venv只读；worktree指定自己PYTHONPATH/cache，不uv写主venv、不默认GBK读文本；固定FFmpeg生产pin不换。Sol本轮quota受限已披露，复工按运行时能力选工，不假称执行模型。
- 已有9个未跟踪.codex/agents角色文件原样保留，不加不删。旧工作树仅在核清未提交内容后退役；失败大媒体先留摘要再回收，不再整树无限备份；测试服务均已关闭，不停止用户原服务。正常提交推送，不force。入口docs/references/creation-guide.md；进度看板第6节是唯一下一步入口。

## 缓存事故接手

见[sprint](docs/exec-plans/sprint-cache-reclamation.md)和[维护指南](docs/references/cache-maintenance-guide.md)。58.29GiB来源已由原工具执行日志、文件时间、具体测试与中断命令闭环证明，不能归因于用户手动删除或Harness要求巨量备份。新工作树只能按需并行放.worktrees，主控/串行复用当前树，最多3个活跃写者；已集成后释放。历史67注册/66可读副本源码逻辑体积约276.9MiB，与58GiB媒体分开；本轮释放2棵约13.6MiB。剩余未知改动不盲删，narration-integration失踪单独记未知，不阻断恢复。新domain/creation_narration.py草稿保留未提交，4个SAPI资产模块仍在旧资产树，恢复时只接精确文件。
