# HANDOFF（覆盖快照）

## 最近一次会话（2026-11-08，自主开发恢复）

Goal active：用户本轮明确恢复自主开发。通用规范AGENTS.md生效；四入口规范已独立提交5809705。用户设计稿/审计报告未动，不git add全目录。

## 本轮恢复核查与验证

知识核心已迁入root，不再次迁移。唯一Sol/high已核知识费用/快照/来源、audio及knowledge.js/narration_drafts.js边界；发现的两项P2均修复并获同一审查者定向复核。编辑代次隔离迟到重合成，asset切换关闭编辑器避免B稿写入A键。4项浏览器定向通过20.79s（.cache/studio-resume-revision-scope.log/XML），含保存版本新旧asset/start/gain/mix回读。

原full session27435于63%主动中止修复第二项P2，不作绿；日志.cache/studio-resume-full-verify.log保留。最终门禁采用.cache/studio-resume-final-verify.log与final-freeze.json；先读日志/查活进程，不重复启动。P020已独立合并baf2a20，规范5809705；main仍8ea3293。余下Studio批次先开发线checkpoint，最终完整绿后再推进main。用户设计稿/工单不整目录add，未真实发送/投稿。

## P033技术集成闭环

main/HEAD/origin-main已核8ea3293；P033完整5054过7跳，静态/CLI全过，session46005终态0，不重跑旧诊断。证据.cache/premiere-readiness-full-verify.log及sprint-premiere-narration-track.md。三格式下载与独立WAV旁白轨已集成，干声不等于完整混音/BGM/图层；P033仍partial，实导/人评未验。

## 当前主线：活动规则+知识策划交付批次

历史P020合并现场（现已baf2a20结束）：P020自动合并无冲突，相关30过0跳79.816秒(.cache/studio-activity-root.xml)。session49998已终态0，.cache/studio-activity-full-verify.log显示5066过7跳1949.77秒、静态/CLI全过，但期间知识写者曾误写root六源码再撤回，父核六路径diff空；源码一致性无法证明，此全量仅诊断，不准当交付绿。事故/工具chunk依据已记sprint-activity-rules.md，日志不改。

验证频率遵AGENTS.md Testing第2条。当前批次是活动规则+知识策划，最终全量暂缓，待知识定向/关键审查/组合集成闭环再冻结写入统一验证。不要为P020单独重跑；main仍8ea3293，尚未发布本批。开发线checkpoint记录定向证据与批次待办，不提前推main。

P020复用本地规则API，状态仍partial。

## 知识与真实媒体证据

preview子树的知识7源码/3测试已由Grok迁入root，来源补丁在R11报告目录；不再次迁移或派重复审查。无资料v1、有资料v2冻结请求/引用已获唯一Sol/high通过，真实AI发送仍未授权。规则/知识全链与旧v1磁盘夹具等缺口不冒充完成。

独立真实媒体链已跑通：.cache/scratch/resume-real-media.py与result.json，日志.cache/studio-resume-real-media2.log；同一隔离repo两条2s fake语音440/880Hz经真实旁白任务/修订、真实FFmpeg、新版180帧30fps6秒MP4、B站七文件ZIP。880Hz幅度0.2447，440Hz 2.48e-7，旧修订所有文件字节保持；包localChecks pass、投稿资格unverified、权利/人评unknown。详见docs/exec-plans/sprint-studio-narration-revision.md。同库任务链随后补证见同一sprint及.cache/scratch/resume-full-journey/summary.json；fake模型一次，R41预算18字未容纳引用，仍未通过；非完整Studio操作/人评。旧门禁期间520源码/测试hash一致，随后补修草稿隔离；最终门禁另记。

## 用户约束与保护

避免PR/AE等大型软件，使用项目FFmpeg/浏览器；专业导出为可选交接，不是成片依赖，实导未验不转人工必做。后续开桌面程序先说名字和目的。Premiere第二次PID43528由用户手动关闭，不是软件故障；未导入XML/开用户项目/确认重置/装CEP/改注册表，不能声称PR全功能控制。合成试件及safe-probe仍在.cache/scratch/。

计数以status.py为准；J1未过，J2/J3未做，不翻人评/passes。

≤3子树，一树一写者，同树pytest串行。共享venv editable指root，env清PYTHONPATH，子树须env后设本树src并核import，完整verify只root。assets树9f4f6ef保留夹具单文件未提交（root已有改进版）；preview树并行知识；core旧副本不覆盖root。stash b55207b68ce12b3682607687c54dc818d1f6f849不drop/pop。旧8765–8769不动，8770已清理，不绕过停8765审批拒绝。原片/证据/账本/标签不改删，不重付重标，不重跑钟馗；无新云/Release/真实发布。免费本机语音，新模型文字发送需独立许可。push走127.0.0.1:7890，不force main，不复制Claude角色到Codex。
