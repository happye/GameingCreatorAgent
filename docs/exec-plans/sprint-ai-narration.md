# AI 按已保存镜头写旁白

R3 / 阶段B · 2026-11-13 · planned

2026-11-14 收尾检查点：纯合同、reasoning service/http/provider及Studio audio接线已写，均未运行pytest、未集成主树，不算交付。UI工人已按用户额度要求中断停笔。静态审查剩余P2：service从application.creation_editing导入version_clips，不支持替换镜头后的revision-v4；应改用ui.revision_jobs.editable_clips并补v4准备/执行测试。另需将待应用commandPreview状态传AudioPanel，避免对尚未保存的助手预览起草。恢复后先审diff并定向验证，再考虑集成；不得启动第二个pytest与已有运行抢共享临时目录。

交付：在Studio声音面板，按当前已保存版本写自然旁白、查看逐句引用后填入草稿，继续用免费本机声音合成。旧模板保留为无模型/超预算/无有效输出的明确兜底，不自动覆盖已挂接音轨或提升质量状态。

## 边界与验收

- application/narration_reasoning.py提供不可变NarrationSnapshot、版本化纯文字ReasoningRequest和结构化输出验证。镜头输入仅clipId/输出帧位置/时长/已保存描述，连同brief、job/plan及父/根回执hash纳入指纹；不发送路径、图像或音频。
- 每句绑定已知且有序唯一clipId，镜头引文必须来自该镜头描述；知识引用限冻结的登记entryId和原文片段。输出时钟由后端映射，模型不能自报时间或媒体身份。引文只证明文字来源，不证明语义。
- 字数上限复用narration_script的CHARS_PER_SECOND及FILL_RATIO；包含最终标点，超出即拒绝，不静默裁短。输出兼容creation-narration-script-v1，带明确AI草稿待人评状态。
- 服务复用现有prepare/execute_budget/显式超额确认、作品预算归属及结果留存；旧schema/prompt/旁白资产读回不变。未知费用保留上界，不自动重试；云配音保持关闭。
- Studio接audio.js（不是只接旧creation.js）。绑定已保存job/plan/receipt；改镜头、切作品、用户修改文字后，旧异步结果不能自动填入。发送前保留恢复身份，丢响应只读恢复。
- 验证：合法与伪镜头/引用/乱序/超时长/越字数、预算内/超限和未知费用、旧模板/资产兼容、真实HTTP假模型→预览填入→本机合成既有链路。纯module不算完成交付，真实模型自然度仍待用户试看。

## 当前分工

task_developer只写独立树的纯应用module和测试，不运行pytest；作品预算批次完整verify正在主树运行。主代理待当前批次闭合后接服务/provider/Studio并统一验证。
