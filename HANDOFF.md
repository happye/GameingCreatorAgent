# 当前交接

更新时间：2026-10-05（Asia/Hong_Kong）。Codex、Claude Code、Grok Build共用；历史见progress.md，验收见feature_list.json。

## 当前结论

root分支codex/visual-details，已提交检查点e9183b3；额度中断后用户授权继续。本轮F010可见细节和图片编号修正尚未完整交付。F006/F009/F010保持false，不能把JSON合法、命中数或UI测试当独立人评。

V5完整Atom运行c78f204907e04eb3a2ac97a9017dcad9保留failed：9/16窗口、24事件。31.5–35.5s两次出现同一时刻31500000us首尾，parser正确拒绝单帧动作。已停止重复V5；V6新增动作优先、自检不同端点及省略单帧外观的提示，仍在独立worker实现，不能松保护或改旧prompt。

## 已实现与验证

- V5独立prompt/hash与1280宽/9图/3MiB/detailoriginal；V1–V4仍512/1MiB，旧hash/parser不变。主体衣着/外观/持有物/环境/效果写成紧凑事实，不确定属性不作正面索引。
- 新正文alias仅能用当前事件已引用的原窗口编号映射真实源时间；未引用/越界编号拒绝。历史事实不重写，用legacy-frame-alias-neutral-v1清理显示/视觉索引/下载；键盘F1和普通标识保留。
- UI显示待核对信息、Completed detailed优先；raw事实与旧篮子身份校验不改。检索bm25-e5-rrf-v5，新passage文本hash与旧向量缓存分开；阈值/否定保护保留。
- 完整verify847passed/1Windows文件symlink权限skip，82.21s；Ruff85/mypy49/CLI/两次离线wheel通过，SHA74728027088611445833fc4cb8802dbcaec8ca1a255b8357e0f91917c6bc459e，日志.cache/detail-verify-final.log。这是V6集成前基线。
- root恢复中的改动包括V6config/store/analysis白名单、detailed-v2、UIprofile、pilot可选V6和CLI displayFacts/run-demo投影；定向66passed（7.92s），真实V6provider/config/hash尚未集成，不是完整验证。

## 真实记录与费用

artifacts/visual-details-atom-execute已完成：28–32及35–39s，A=V4/512、B=V5/512同九帧，C=V5/1280同源时刻。A/B/C均3事件，两静图空、两倒序发送前拒绝；8HTTP/72图，估价¥0.03676864，unknown0。全部冻结源/hash/配置/费用；dry和1280证据预览保留在独立目录。

V5部分运行共12HTTP、估价¥0.07282904、unknown0，含一次uncertainty错误与两次同端点错误。合计本轮¥0.10959768，非账单；后续合计实际及未知承诺上限¥5，不能重置失败费用。下一V6run最多¥4.89040232，若先做V6pilot需再扣其承诺。

细节增加已观察到，但35s护目镜/发饰、围巾色、28s持有物分类仍可能误判；38–39sC跨剪辑声称连续移动。任意复合属性AND/同一主体保证、静态外观独立索引未实现，见TD007/TD009。

## 当前可用Demo

双击Start-Workspace.cmd隐藏启动项目内Python并打开浏览器；重复启动复用，启动不分析或付费。http://127.0.0.1:8765/已只读核对本仓库health PID2548/parent34124，与.cache/workspace/port-8765.json一致（重启前必须重新核对）。用户在额度中断期间已启动新代码，旧PID36692记录过期。

当前可检索Completed Atom仍为96b5f01530ce43e2944828fb0520b9b4：54.743220s/V4/16窗口40事件，估价¥0.05029788。旧漫画f76f5d6495314c04ae04083614d4afd6保留。失败V5可查看已完成时间轴，但不能当完整检索demo。新V6完成且浏览器验证后再设为默认。

## 归属与恢复顺序

- detail_v6_completion：现有.worktrees/detail-v6/codex/detail-v6，独占deepseek_vision.py、test_detail_action_eligibility.py、sprint-detail-v6-worker.md；接着断额度前未提交实现，禁止回退root的事件引用保护。
- root：配置/SQLite/analysis/CLI/UIprofile、pilot版本支持、真实调用、共享文档及集成。其余V5vision/presentation/pilot worktree冻结，禁止覆盖root。
- detail_retrieval_audit：只读CLI/旧篮子/向量身份复核和后续精分析建议，无编辑/API。

1. 先核对git status/HEAD/owner与worker未提交状态，保存当前改动，集成V6独占提交并钉实际promptHash；旧V5及failedrun不改。
2. 验证V6合同、配置与续跑，冻结31.5–35.5s真实对照（含静图/倒序）；所有尝试逐case记录，修复单帧误报才生成完整新run，不重放旧请求碰运气。
3. 完整新run后查细节查询三模式、真实浏览器播放/证据/显示/下载/旧数据不变；核对当前health与PID记录再重启自有服务，启动脚本仍不付费。
4. 完整verify、规格/API/手册/feature_list/assignments/progress/HANDOFF同步。GitHub上次443超时，当前只读重试中；本地commit不等于远端已同步，禁止强推或全局网络配置。

环境只能在.tools/.venv/.cache，先env.ps1+Python -B；密钥只使用现有进程DEEPSEEK_API_KEY，不打印/复制聊天密钥。长任务和每个验证节点主动落盘/提交，不等额度提醒。完整实现历史与失败明细见docs/exec-plans/sprint-visual-details.md；旧V4记录见sprint-temporal-gameplay.md。
