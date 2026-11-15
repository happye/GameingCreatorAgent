# 阶段 C：完整受支持编辑草稿恢复

R2 / 阶段C · P032、P040 · 2026-11-15 · 已集成，定向验证通过

范围：本机 v2 快照保存镜头五字段、字幕覆盖、audioMix（含原声 envelope）、旁白选择。新替换和新图层仍 partial；父绑定继承。既有 v1 key/元组不变，v1 原字节可读，打开/恢复不迁写，下次有效编辑才写 v2。

验收：
- 整 payload SHA256 和 scope/epoch 防旧写；白名单不保存 asset、URL、路径、证据或费用身份。
- 显式恢复 v2 才 POST draft-restore-preview；后端只读链校验项目/回执，复用修订和音轨来源校验，按新 frames 校验旁白实际时长，返回已验证 public asset。
- 字幕清空、镜头删除、原声 envelope、配乐及旁白位置/增益/闪避原子恢复，一步 undo。
- 错回执/外项目/缺失/越长/URL 注入整份拒绝，现场与原快照保留。
- 父 v4 由可信链注入 manifest，新 replacements 为空；父图层继承。
- 编辑/undo/reset/discard/新恢复/切作品/卸载和 live 任务令旧响应失效，GET/hash/projection 每次 await 后重验。
- 成功保存清父 key，失败保留；恢复不创建 job、不合成、不调用模型，jobs/账单/证据原字节不变。

验证终态（本树具名定向，共49个独立节点闭合）：
- 114204.log：1过、15失败、33 setup错误；原因是本树缺 `.tools` 与新fixture未补根镜头 speed/transition 默认。建立主树工具junction、补测试默认值后，只按保存的48个失败节点复跑。
- 114306.log：quiet关闭cacheprovider，`--lf`参数不支持，未运行测试；随后用原失败节点清单显式选择。
- 114322.log：47过1失败；仅慢投影scope测试的mount移除DOM却未卸载旧Preact hook。只在本文件mount补显式卸载；114552.log复跑慢投影参数组3过，原失败闭合，未改生产边界。
- 后端新/继承本机旁白、实际时长/回执/外项目/缺失拒绝、父v4及父图层、字幕清空、envelope、真实BGM/旁白恢复、真实Studio刷新→手动恢复→显式保存均通过；仓库文件字节不变断言通过，无真实模型/云配音/发布/支付。
- Ruff/格式、单模块mypy、两个JS模块语法、diff检查通过；新Python函数61行。唯一task_quality_guard静态审查通过（由主代理执行）。无pytest遗留。

主树集成：两具名文件49 passed（`.cache/test-logs/pytest-20261115-162519.log`）。独立树日志位于`.worktrees/full-edit-draft/.cache/test-logs/`；唯一关键边界代理审查通过，测试fixture修复没有生产边界增量。

完整门禁另计：主树18e9e2d此前完整运行5363过10跳1失败（试听同步间歇偏差），不包含本v2切片；原失败单节点114035.log复跑1过，根因未定位，TD030交Grok。该完整运行仍记失败，不由本树定向通过冒充全绿；按用户收尾要求未重跑完整门禁、未Release、未改变旅程/人评状态。
