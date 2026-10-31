# 当前接手：旁白与解说草稿已交付，下一自然语言改时间线

2026-10-31解说脚本P025已交付（部分，首产品★）：旁白面板“按已保存镜头生成解说草稿”，用已保存版本各镜头的分析描述与成片时长，离线模板生成中文草稿（按本机Huihui实测约3.7字/秒、预算3.5字/秒×90%），按成片时间均匀取镜头、去帧号标记、不补词不加省略号，填入旁白文字后可修改再生成试听；页面如实标“模板草稿，待人工核对”及未写入镜头数。11项新测试（单元/任务/HTTP/浏览器）及113项相关回归、Ruff/mypy通过；真实12秒方案生成36字（约10.0秒）草稿，覆盖首镜头与第349帧末镜头。真实页面按钮未手点（历史列表加载慢，见TD019②），以浏览器测试代替；单Agent简单改动，无费用/持久化边界。P025未开始→部分：51项10/21/20≈40%，首产品22项0/13/9≈30%；人工0/未来8，债务19项11/2/6不变。下一自然语言改时间线（规则版）。

2026-10-31本地旁白R2-I已交付（P026部分）：工作台选本机声音（默认中文Huihui）→输入文字→生成可试听WAV→按成片秒数挂接、独立音量、可选“旁白时压低原声和配乐”→保存版本/继承/移除/祖先恢复→真实MP4与旁白文本下载→封面文案→B站七文件包。165项定向测试（17真实FFmpeg混音、25任务/版本、6浏览器及编辑/包回归）、Ruff/mypy通过；唯一code-quality-guard关键评估PASS（0 P0/P1；6个P2中收据混音策略、迟到取消回收、无关输入阻挡已修，另3项记TD019）。真实Huihui 5.688秒旁白挂3.000秒：成片360帧/30fps不变，互相关峰值正好3.000秒，旁白期间原声约降4dB后恢复；声音商用许可未知。P026未开始→部分：51项10/20/21≈39%，首产品22项仍0/12/10≈27%；人工现在0/未来8。TD018已解决（60棵旧工作树全部退役，未提交改动以提交保存于各自分支；narration-integration“失踪”系被误建在narration-mix内部）；新增TD019，债务19项11/2/6。下一步P025解说脚本：方案片段描述→可编辑脚本→一键送旁白。

## 已能使用与证据

- 工作台需求→三模板方案/草稿/缺口→真实MP4预览下载；镜头裁短/换序/删除、不可变版本与祖先恢复；手写/改词/关闭/恢复字幕、SRT与中文烧录；本地曲库、双音量、duck、混音继承/移除。
- 2026-10-31封面文案：成片选帧PNG、标题/简介/Tags版本与五文件下载。60定向测试、5源码mypy/Ruff、Sol/high关键评估PASS；真实第6/34帧RGB一致，旧视频SHA不变、刷新0POST/新实例0worker。合同sprint-publication-assets.md。
- 四平台本地预览包：可编辑preset→横竖视频/封面→七文件ZIP/Preflight。47联合+3增量，8源码mypy/Ruff、Sol/high PASS；四平台实际35帧/音轨/ZIP通过。规则仍为本地preset、权利/真人质量未知，test_only音乐会blocked。合同sprint-platform-packages.md。
- 最近已交付逐镜头0.5x/1x/2x：源范围不变、保音高原声/字幕跟随、BGM输出时钟、祖先恢复；138主树联合+19最终渲染增量、5源码mypy/Ruff通过。真实40→17→祖先35帧，SRT1.000/.233/.500秒；新40帧成片末帧封面和包通过，刷新0POST/新实例0worker。
- 变速评估：Sol/high初审发现补尾P2已修后触发额度限制；已向用户披露Astra/low完成最后两处增量的限定静态PASS，不冒称Sol复核或任意音频瞬态样本级对齐。证据.cache/clip-speed-main.xml、clip-speed-real-browser.json、clip-speed-downstream.json、clip-speed-mobile.png；最终19项在clip-speed-render树.cache/speed-concat-final.xml。已交付源码eb6addf已推送并核远端。

## 最近交付与当前下一步

转场已完成[合同](docs/exec-plans/sprint-clip-transitions.md)及真实UI29/37/35帧与下游末帧封面/包验证；证据.cache/clip-transition-main.xml、clip-transition-refresh.xml、clip-transition-real-browser.json、clip-transition-overlap.png、clip-transition-mobile.png。先前未完成补丁保留为历史，禁止重新应用覆盖当前实现。首次QA只在刷新恢复超30秒处停止，已生成6job完整；修复历史列表阻挡后复用它们续测，未重复渲染。普通短字幕已查看，任意长文排版不保证；SRT播放器自行决定重叠布局。

R2-H已按[候选替换合同](docs/exec-plans/sprint-clip-replacements.md)完成：真实双run根只用Atom仍能选漫画候选，四成片6/5/6/5帧及末帧封面/包，旧手写字幕清除/祖先恢复通过。证据.cache/clip-replacement-delivery.json（严格JSON整合原流与最终预览）、clip-replacement-main.xml、asset.xml、clock.xml、preview-verified.json、cross-run.png和mobile.png。旧预览unsupported诊断原样保留；10秒有界定位最后严格通过，不能重新跑四成片补证据。根request仍是唯一候选来源范围，v4独立重建，旧根/v1-v3不放宽。

R2-I本地旁白已按[合同](docs/exec-plans/sprint-local-narration.md)交付（结果见合同末节）；证据.cache/narration-main.xml（165项）、narration-ui.xml、narration-real-render.json（真实3.000秒定位）。剩余P2见TD019。

P025解说草稿已交付（见[sprint](docs/exec-plans/sprint-narration-script.md)）。下一自然语言改时间线规则版（首产品★）：在编辑器输入“前5秒太慢”“删掉第3个镜头”“整体慢放一半”等常见中文指令，确定性解析为可预览的镜头修改（裁短/删除/换序/变速），用户确认后保存新版本并可撤销；无法识别的指令明确拒绝，不调用付费模型。随后三种内容模式端到端与桌面EXE。

## 状态与边界

- 整体51项10已交付/19部分/22未开始≈38%，首产品22项0/12/10≈27%；转场属于既有部分功能的内部能力，不增加数字，P028/P029/P032仍部分。质量线真实0/8，F006/F009/F010 false；不因此全局停止创作/桌面/商业化开发。
- 用户现在必须人工操作0项，未来8项按[user-actions](docs/exec-plans/user-actions.md)量化触发；技术债18项10已解决/3部分/5未解决。本次无新产品Provider请求/下载/真实发布，不重新申请已用过的旧许可；未改素材、旧分析、费用、人工记录。
- 旧暂停直接由额度提醒触发；当前已恢复，项目未完成。复工直接续做，不要求重新讲历史、补片、分组或重做标注。
- Windows PowerShell，先scripts/env.ps1，主Python -B/共享venv只读；worktree指定自己PYTHONPATH/cache，不uv写主venv、不默认GBK读文本；固定FFmpeg生产pin不换。Sol本轮quota受限已披露，复工按运行时能力选工，不假称执行模型。
- 已有9个未跟踪.codex/agents角色文件原样保留，不加不删。旧工作树仅在核清未提交内容后退役；失败大媒体先留摘要再回收，不再整树无限备份；测试服务均已关闭，不停止用户原服务。正常提交推送，不force。入口docs/references/creation-guide.md；进度看板第6节是唯一下一步入口。

## 缓存事故接手

见[sprint](docs/exec-plans/sprint-cache-reclamation.md)和[维护指南](docs/references/cache-maintenance-guide.md)。58.29GiB来源已由原工具执行日志、文件时间、具体测试与中断命令闭环证明，不能归因于用户手动删除或Harness要求巨量备份。新工作树只能按需并行放.worktrees，主控/串行复用当前树，最多3个活跃写者；已集成后释放。历史67注册/66可读副本源码逻辑体积约276.9MiB，与58GiB媒体分开；本轮释放2棵约13.6MiB。剩余未知改动不盲删，narration-integration失踪单独记未知，不阻断恢复。新domain/creation_narration.py草稿保留未提交，4个SAPI资产模块仍在旧资产树，恢复时只接精确文件。
