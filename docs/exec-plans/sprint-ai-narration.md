# AI 按已保存镜头写旁白

R3 / 阶段B · P025 · 2026-11-15 · 已集成，待本批完整门禁

2026-11-15：已修revision-v4读取与未保存助手预览阻断（ready及epoch同时失效）；真实HTTP使用假模型、手动采用、本机合成、丢响应/400只读恢复、改文字/切版本/切作品失效及离线模板均有定向证据。独立关键边界审查通过后集成主树，不以假模型证明自然度。

交付：在Studio声音面板，按当前已保存版本写自然旁白、查看逐句引用后填入草稿，继续用免费本机声音合成。旧模板保留为无模型/超预算/无有效输出的明确兜底，不自动覆盖已挂接音轨或提升质量状态。

## 边界与验收

- application/narration_reasoning.py提供不可变NarrationSnapshot、版本化纯文字ReasoningRequest和结构化输出验证。镜头输入仅clipId/输出帧位置/时长/已保存描述，连同brief、job/plan及父/根回执hash纳入指纹；不发送路径、图像或音频。
- 每句绑定已知且有序唯一clipId，镜头引文必须来自该镜头描述；知识引用限冻结的登记entryId和原文片段。输出时钟由后端映射，模型不能自报时间或媒体身份。引文只证明文字来源，不证明语义。
- 字数上限复用narration_script的CHARS_PER_SECOND及FILL_RATIO；包含最终标点，超出即拒绝，不静默裁短。输出兼容creation-narration-script-v1，带明确AI草稿待人评状态。
- 服务复用现有prepare/execute_budget/显式超额确认、作品预算归属及结果留存；旧schema/prompt/旁白资产读回不变。未知费用保留上界，不自动重试；云配音保持关闭。
- Studio接audio.js（不是只接旧creation.js）。绑定已保存job/plan/receipt；改镜头、切作品、用户修改文字后，旧异步结果不能自动填入。发送前保留恢复身份，丢响应只读恢复。
- 验证：合法与伪镜头/引用/乱序/超时长/越字数、预算内/超限和未知费用、旧模板/资产兼容、真实HTTP假模型→预览填入→本机合成既有链路。纯module不算完成交付，真实模型自然度仍待用户试看。

## 验证与接手

以下定向日志保留在 `.worktrees/ai-narration-script/.cache/test-logs/`，未复制或改写原记录。

- 首轮7文件：81 passed、2 failed；日志`.cache/test-logs/pytest-20261115-102528.log`。失败为新测试写错保存文件位置、旧模板异步测试未等配置查询，已修复。
- 修复/新增AI回归：10 passed；日志`.cache/test-logs/pytest-20261115-102726.log`；该轮旧模板等待字符串被CSP拒绝，随后改函数等待，单独1 passed（`pytest-20261115-102932.log`）。
- 首次收集环境失败单独留证：`pytest-20261115-102444.log`；复用主树运行时后显式`-o pythonpath=src`，实际导入已确认来自本工作树。未安装依赖。
- Ruff与mypy受影响4业务模块通过。未运行全量verify/Release，未真实AI/云配音/上传/发布。最终AI与旧模板浏览器两文件15 passed（`pytest-20261115-103012.log`），含预览及采用后真实引用出处可见。
- task_quality_guard唯一费用/身份审查：首轮1个P2（模板文字失效后busy未释放），修复后增量复核通过，无其余新增P1/P2；未重复派普通审查。自然度、语义及听感仍需用户用实际素材试看。

- 审查P2增量：模板文字失效与busy任务ownership分离，AI模板按钮遵守本机任务busy。延迟模板期间输入不被覆盖，随后本机合成、保存可继续：新增节点最终1 passed（`pytest-20261115-103313.log`）；前轮`pytest-20261115-103221.log`为1 failed、1 passed，其中旧迟响应节点通过，新增测试错误要求未修改版本能保存。修正断言到合成挂接后通过，未改业务规则，不把失败轮称全绿。
- 主树集成：8个具名文件138 passed（`.cache/test-logs/pytest-20261115-103633.log`），覆盖纯合同、服务、HTTP/provider、作品预算及新旧旁白浏览器。Dashboard源与生成数据已同步；本批完整门禁留到与下一独立切片共同结束时运行一次，未Release。
