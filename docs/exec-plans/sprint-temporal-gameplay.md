# F006 玩法时序理解修正

## Codex恢复复核与v4进行中

provider d026103已集成为42604f9；最新配置真实hash为9ea350e10eb028f1f5e2dc7d355ebd1d080ad8ae8397eb709705a25773323f48。联合相关测试217 passed/1权限skip（5.48s）、Ruff/mypy48通过，旧v3 hash未变。即将运行同0–4秒的有界v4试验，输出全新artifacts/temporal-v4-execute-0，费用/新结果尚未知，F006/F009未验收。工具收据检查发现28个stdlib pyc漂移，仅从固定SHA归档恢复这些文件，receipt/程序/DLL未改，完整init随后通过。

已将Grok集成全量保存4c37a63。费用/失败/冻结manifest与交接一致；v3只记录evidence_outside_range，缺原响应与坏区间，不能确定具体端点错误。新增v4设计用起止frame alias替代模型微秒算术，程序映射为SourceRange，旧v3保持不变；有限白名单结构诊断可定位新失败，不记录原模型文本。root已支持新配置/store/analysis/pilot（附同帧C对照），新增本地health识别给一键启动器；定向配置/pilot/HTTP已通过。本轮尚未执行新收费调用或宣称动作检索改善。

temporal_frame_contract/workspace_launcher在独立worktree实现各自独占文件。新完整verify和浏览器/真实API待集成后完成。根目录一键启动需求已分配，不再让用户仅手动起服务/复制URL。F006/F009仍false。

日期：2026-10-04；owner：Codex root。用户明确否决当前截图式描述的玩法检索效果：打Boss、跳跃玩法、射击玩法均找不到。此为真实用户定性未通过反馈，不虚构为已录入独立固定十槽U10。

## 根因与范围

v2每请求已有5张按sourceUs排列的图，1FPS/1帧重叠；不是每帧独立API。但提示允许单帧事实与[T,T+1)事件，校验只验证引用/时间/JSON，没有要求多帧动作依据。事件索引因此可能是“有什么”而非“正在做什么”。检索改词/降阈值不能产生缺失的动作理解。

本轮优先修正分析：新增独立版本的连续动作prompt、9帧有序窗口与密采样试验，要求变化过程、多时间证据与保守机制判断。枪/巨型敌人/空中姿态不能单独证明射击/Boss战/跳跃。旧run与prompt保持不可变，新配置创建新run。保留Provider调用前账本、预算、取消、成本未知与已有预览/选片合同。

## 可验证目标

- 新prompt按整段序列描述主体→动作变化→可观察结果，避免逐图清单；不足证据允许空事件。
- 动作事件至少引用两个不同源时间的有效证据；同图复制、倒序/重复时间、未见时间范围、单帧机制断言须拒绝。
- 正式API支持多图不等于有可靠时序理解；先小范围原PV新旧对照，记录全尝试用量、费用、输出、错误与边界。
- 冻结同时间覆盖的v2稀疏5帧、v3稀疏/密采样9帧对照；开发诊断不代替独立F006。
- 不无条件跨窗拼接动作，不跨镜头伪造故事；独立动作分段/候选精分析根据实测再展开。

## 任务归属与恢复

root在codex/temporal-gameplay拥有配置读取/analysis窗口、实验脚本、共享规格/验收/HANDOFF。视觉provider worker须独立worktree，仅拥有deepseek_vision.py、新temporal测试及自己的sprint。只读audit/acceptance核对链路/官方限制/验收，不写root。

实际分工：temporal_vision在.worktrees/temporal-vision实现provider；temporal_pilot在.worktrees/temporal-pilot拥有validate-temporal-gameplay.py/其测试/own sprint。root另拥有sqlite_store.py的配置白名单兼容（不改schema/旧快照）及test_temporal_analysis.py。初次定向测试暴露了存储白名单仍限5帧与fixture缺prompt hash，已定位补齐；pytest缓存改用独立目录，不处理其他用户锁定缓存。

root配置/存储/窗口定向39项通过（独立pytest tmp/cache，warnings=error），mypy48源文件通过。新增pipeline身份phase0-analyze-temporal-v1，v3允许2–9帧，v1/v2仍5帧，旧schema/快照未重写；run-demo支持显式-Config。provider/实验worker尚未集成，无新API调用，F009false。

起点317b22d：F008工作台技术验收已通过，F006仍false。进程DeepSeek key配置存在，仅检查布尔值；不读取到日志/文件，不复制聊天密钥。全依赖/工具继续项目隔离。集成前的实现、实验与最终检查当时尚未完成。集成后的实测见下一节，仍不能宣称玩法问题已解决。

## 2026-10-04 root 集成与一次有界对照

root 接入 vision provider（对外 `max_images` 9，v1/v2 仍拒绝超过 5 张，旧 hash 不变）和 pilot。`config.temporal.example.json` 的 `promptHash` 是 `27762b0b9d390c64d53ec4be815bd6e8ead4d249ec9864bb87735223b3ad1c4d`。`config.example.json` 未改。时序定向 151 passed。`./scripts/verify.ps1` 退出 0：618 passed、1 skipped（34.28s），Ruff 76 文件，mypy 48 源文件，wheel `b37b039a4c8688d9320b0bd8a29521306d57a970c26900660f951e679938f52f`。F006 与 F009 仍 false。

同一 PV（sha256 `e4ad1f974910639b7914fec1b668e6cbea3d331721b08b56268ee548f8b7619a`）两次无 `--execute` 冻结在 `artifacts/temporal-gameplay-dry-1` 与 `artifacts/temporal-gameplay-dry-2`：2 FPS，0–4 秒，A 为 v2 的 5 帧，B 为 v3 的 9 帧，加静帧和倒序；`qualityGate` null，无 HTTP。`--execute` 一次，目录 `artifacts/temporal-gameplay-execute-1`，退出码 4，`completed_with_failures`。v2 返回 5 条事件；v3 被 `evidence_outside_range` 拒绝并记录估价 ¥0.003524；静帧返回空事件，没有确认连续动作；倒序在发送前被本地拒绝，费用未知。已知估价合计 ¥0.0075876，未对账单。这不是玩法检索通过。

磁盘复核：`config.temporal.example.json` 的 promptHash 等于 `vision_prompt_fingerprint("phase0-vision-v3")`；`git diff -- config.example.json` 为空。两次 dry-run 报告都是 `frozen`、executed false、qualityGate null。execute-1 报告是 `completed_with_failures`、executed true、qualityGate null。provider 与 pilot 文件在 root 工作区。

下一条工作：查看 `artifacts/temporal-gameplay-execute-1` 里 window-0-B 的 `evidence_outside_range` 拒绝，收紧 v3 提示让被引用帧落在半开区间内，先用离线视觉测试证明，再对同一个四秒窗口重跑一次有界 `--execute`。不要全量重分析 PV，不要把 F006 或 F009 标成通过，不要宣称打Boss、跳跃或射击已经修好。
