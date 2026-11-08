# HANDOFF（覆盖快照）

## 最近一次会话（2026-11-08，自主开发恢复）

Goal active。通用规范AGENTS.md生效；四入口AGENTS/CLAUDE/CODEX/.grok/rules/project.md未提交，独立提交方案尚未另执行，不混业务。用户设计稿/审计报告未动，不git add全目录。

## P033技术集成闭环

root开发线codex/timed-overlays-20261107。本批业务合并30a94a4，提交/远端实际SHA以git为准；architecture/API两处EOF冲突已保留两边，无源码冲突。当前完整门禁已结束，不能再把session46005当活进程或重复启动。

最终.cache/premiere-readiness-full-verify.log：5054通过/7跳过1794.68秒，488文件格式/Ruff/mypy209源/CLI全过，session46005终态0。root相关47过153.124秒，子树35项及唯一Sol/high专项通过。P033为Studio三格式保存基线下载、HTTP错误/迟到下载隔离，XMEML只读核验WAV独立旁白轨、真实格式/输出帧、None旧字节保持。干声不等于完整混音/BGM/图层交接；P033保持partial，实导与人评未验。

首轮.cache/premiere-integration-full-verify.log：1失败/5053过/7跳1998.64秒，CLI未执行。test_speculative_seek_does_not_freeze_music启动等待失败，未进主体；现场.cache/pytest-runs/fc45f2d3cb2940c884c93394475afa69保留。Sol/medium用750ms Worklet延迟确定触发同类问题：静止模拟时钟无后续同步，推进timeupdate即恢复；不声称取得原失败逐事件轨迹。仅补夹具graph.ready，parent有界node/failed等待，不改生产播放/DSP/阈值/原断言。assets树受控旧失败→新过日志.cache/scratch/playback_delayed_before_after.log；文件16过、相邻音频10过；root16过35.130秒(.cache/playback-readiness-root.xml)。合同sprint-premiere-narration-track.md已补最终证据。

前一批main3b345d0交字幕即时预览/多平台包/Worklet采集修复，完整5035过7跳1723.43秒（.cache/r2-audio-worklet-full-verify.log）。无需再跑这一批，人评及P029/P035整项未提升。

## 下一步：接入Studio活动规则

preview树codex/studio-activity-rules-20261108，d28d668已推、干净；从3b345d0起步，旧P033分支30a94a4保留。复用现有本地规则API接Studio：提取、原文行/页数、显式填当前Brief、再生成真实离线计划；无模型/新依赖/大型软件。合同复用docs/exec-plans/sprint-activity-rules.md末节，当前该合同仍未混P033提交。

仅4文件：studio/activity.js、edit.js规则入口、server.py静态白名单、tests/test_studio_activity_rules_browser.py。最终12过0跳26.723秒，Ruff/format/mypyserver通过；preview树.cache/scratch/studio-activity-rules/results.xml。唯一Sol/medium审查P2为普通input剥换行使话题再编辑粘连，改逗号并在原测试验证再次编辑后4主题独立；parent核修复和结果。text/file-viewport.png已目检三栏/播放器/左栏滚动正常，旧窄长裁图不用。OCR/PDF旧后端证据沿用，尚未root集成/完整门禁，不提升P020整体或人评。先核P033实际提交推送完成，再merge d28d668，按变更更新使用指南/feature证据和验证。

## 用户约束与保护

避免PR/AE等大型软件，使用项目FFmpeg/浏览器；专业导出为可选交接，不是成片依赖，实导未验不转人工必做。后续开桌面程序先说名字和目的。Premiere第二次PID43528由用户手动关闭，不是软件故障；未导入XML/开用户项目/确认重置/装CEP/改注册表，不能声称PR全功能控制。合成试件及safe-probe仍在.cache/scratch/。

最近status.py --check：51=10交付41部分，质量0/51，F8/3；债25=17解决3部分5未解，人工9。J1第四次not_usable，J2/J3未做，不翻人评/passes。

≤3子树，一树一写者，同树pytest串行。共享venv editable指root，env清PYTHONPATH，子树须env后设本树src并核import，完整verify只root。assets树9f4f6ef保留夹具单文件未提交（root已有改进版）；preview树d28d668干净；core树旧副本不覆盖root。stash b55207b68ce12b3682607687c54dc818d1f6f849不drop/pop。用户旧8765–8769不动，8770已清理，不绕过停8765审批拒绝。原片/证据/账本/标签不改删，不重付重标，不重跑钟馗；无新云/Release/真实发布。免费本机语音，新模型文字发送需独立许可。push走127.0.0.1:7890，不force main，不复制Claude角色到Codex。
