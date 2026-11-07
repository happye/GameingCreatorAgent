# Studio 逐镜字幕编辑

2026-11-07，延续R2制作主链/P029，不把已有后端字幕能力误当Studio已经可操作。Luna/high只读核实：ClipInspector现有裁剪/速度/转场/替换，无字幕表单；保存时仅把原editor.subtitleOverrides带回，缺本地编辑状态。

## 合同与归属

- Sol/medium唯一写树 `.worktrees/j1-preview-corrections`，分支 `codex/studio-captions-20261107`，基线1c8217e。仅持有studio/clipedit.js、edit.js、reasoning.js必要generation键及新browser测试；主控持合同/集成/文档。root正在组合完整verify，禁止改root受测源码。
- 复用revision既有`subtitleOverrides=[{clipId,text}]`，不新增schema/service/provider。空数组清除全部覆盖；单层空串表示该镜头无字幕；删去单层覆盖恢复原片转录自动字幕（存在转录时）。纯文本/换行/2000字符限制沿用既有domain，不能有损trim。
- ClipInspector有镜头字幕textarea、手写/自动/不显示状态及“恢复自动字幕”“此镜头不显示字幕”按钮。输入即时更新，非法文字显示原因并阻止保存/导出。
- ClipEditor加载、修改、dirty、保存、撤销、重开携带本地字幕状态；删除镜头滤覆盖，替换源画面清该镜头覆盖，不能把旧手写误带到新画面。只调整成片字幕，不改变原始转录、录像、分析或证据。
- adoption与reasoning等待期间出现字幕修改也令旧建议失效；不改变费用/确认/请求恢复机制，不发真实云调用。

## 验收

真实Studio/HTTP保存→刷新重开、手写→空覆盖→自动、撤销及换镜头清覆盖；适当真实SRT/烧录证明覆盖生效。现有caption/edit/replacement后端回归复用，原转录字节保持。fake规划/声音不冒充人评。子树env后显式设置自身PYTHONPATH及独立pytest临时目录；禁止误跑共享venv指向的root实现。

独立树已实现并通过：`.cache/caption-tests.xml` 24项（新浏览器4+既有后端20），`.cache/caption-browser-final.xml` 7项（新4+旧Studio编辑1/替换2）。两组有重叠，不相加。真实MP4/SRT、空覆盖/自动/撤销/刷新、替换禁编→保存新ID恢复、删除过滤及切方案隔离均有证据。原转录不变复用既有后端测试与本次只改覆盖数组的证据，不冒充真人判断。

Sol/high审查发现并闭环P2：未保存替换仍使用旧clipId，而v4保存会重命名，故暂禁该镜头字幕控件并提示先保存；保存加载新身份后可编辑。最终审查通过（只读源码/XML，未独立重跑pytest），Ruff/格式/diff检查通过。

尚未集成root或计交付；等待root叠加组合门禁结束，再集成本批并执行所需门禁。即时预览不显示字幕，界面明确要求导出页选择SRT或烧入字幕。完整P029排版/质量与真人创作验收继续按全功能路线推进。
