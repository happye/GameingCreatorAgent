# HANDOFF（覆盖快照）

## 最近一次会话（2026-11-14，用户周额度不足2%要求收尾）

停止新增开发，暂停自主goal；用户恢复后继续AI旁白，不把WIP当成交付。所有工人均已停笔，无后台pytest留跑。

## 主树已交付并推送

当前分支codex/knowledge-version-compare-20261108，能力提交da2212c：显式新建/恢复作品，需求→多次根方案→AI采用→修订/导出同作品预算；月¥30、同作品跨月¥1。新prepared冻结work或可信legacy根预算键，坏链消费全局?，旧账本/已付费版本不改；草稿/最近任务/待恢复brief按作品隔离。导航意图消费不改变已挂载editor的open依赖，切布局不丢dirty修改。TD029已解决，旧无work草稿保守兼容。前一主题编排056b252已交付，旧v1/v2回放保持。

## 验证终态（不要再跑本批全量）

quiet.ps1 verify在da2212c完整通过：5294 passed、10 skipped、0 failed，2353秒，格式/Ruff/mypy/CLI通过，未Release。日志.cache/test-logs/verify-20261113-235154.log，verify-last.json=passed，原工具会话17940已终结。

受影响94文件1078过3跳1失败（旧测试要求把A状态消息显示到B）。改为B不显示A状态，保留任务登记/原草稿不变断言后，最终作品浏览器+该节点9过（pytest-20261113-234838.log）。关键守卫静态增量通过；无真实AI/云配音/发布/支付。Dashboard/合同/STATUS已同步。J1/J2/J3人评不变；第六次J1待用户方便时复测，旧8765需重启。

## 下一片AI旁白：独立WIP，尚未集成

.worktrees/ai-narration-script，分支codex/ai-narration-script-20261113，WIP提交65f1302已推远端，base da2212c。纯module、reasoning service/http/provider与Studio audio接线及测试均保存；未跑pytest，不算交付。合同docs/exec-plans/sprint-ai-narration.md在该树。工人narration_ui因用户收尾中断，需审其未完成测试/接线。

恢复后的明确先手：
1. 修已证P2：service从application.creation_editing导入version_clips不支持替换镜头后的revision-v4，应复用ui.revision_jobs.editable_clips包装；补v4 prepare/execute回归。
2. AudioPanel需接收待应用commandPreview状态并禁AI准备/采用，不能只检查editing.dirty。核对新UI的scope/用户改文字/丢响应含400只读恢复、模板兜底与手动“填入旁白稿”。
3. 在该树运行具名纯module/service/browser测试，再集成；先load主树env，借主树venv，不重新安装。测试主树先已无运行，严禁同时起两个pytest。
4. 真正入口是Studio audio.js，不是旧creation.js；复用作品预算/发送门/原输出留存，免费本机合成，云配音不启用。新的旁白schema8192与报价/预算/发送绑定；人评自然度不能由fakeTransport测试冒充。

## 保护

.worktrees/work-budget-identity是旧工人草稿，主树有后续修复，不能反向覆盖；暂留。AI旁白树、四个更早worktree、stash、用户未跟踪设计稿/审计/Grok工单均不动。原片/标签/账本/证据不可改；未知费用不写0、不自动重付。未Release、未合main。推送git -c http.proxy=http://127.0.0.1:7890 push。
