# J1 反馈迭代合同（2026-11-04）

目标：解决第四次试用的七组反馈，沿全功能路线继续开发；语音暂用免费本机声音，不发送新付费请求。保留原素材、分析事件身份、源时钟、证据和账本。模板/规则不冒称开放式 AI 已完成，J1 人评不由开发测试代填。

## 本轮实现与验收

1. 素材箱按文件身份合并展示，分析尝试保留为版本；搜索默认当前录像，全部搜索明确跨游戏且同源只取一个选中/可用分析版本。浏览器覆盖重复/失败分析、跨游戏相同玩法词和范围切换。
2. 短/瞬时分析事件与剪辑选区分开。建议上下文区间可回看/改动，篮子、方案、版本、渲染使用同一选区；后端核对原事件/媒体/时长/证据，不改模型事实区间。测试包含越界/错源/错误eventId/瞬时事件到实际渲染的边界。
3. 素材单片段播放在终点停止，重播回起点；保留查看整段录像入口。剪辑 seek/缓冲时旁白/BGM暂停，恢复统一校音，主动后退仍允许；补浏览器媒体事件回归。
4. 保存按钮禁用原因可见；镜头/声音修改可保存并重开。平台包指定真实文件名，浏览器点击验证ZIP字节/下载事件，原true.txt原因未证实前不称原故障已解决。
5. 即使云Key存在也默认本机免费声音；无本机声音不自动回退付费；保留显式云选项的费用门，测试不调用真实云端。

## 所有权与验证

- 主控：素材/搜索/篮子/取景UI、保存/下载/免费默认、集成与文档。
- task_developer Sol/medium：独立 `.worktrees/j1-preview-corrections`，仅 preview.js/useAudioPreview/播放回归测试；另一位在 `.worktrees/j1-selected-ranges` 负责选区后端及测试。二者不提交，主控集成，其他未跟踪设计文档保持。
- task_explorer Luna/high 完成路径定位；task_reviewer Sol/medium 提供验收。选区身份/证据边界最终使用一个 task_quality_guard Sol/high 评估，不叠加普通重复审查。
- 定向 `test-affected.ps1 -Browser`；里程碑 `verify.ps1`；界面在真实浏览器走用户操作。不在测试运行时改文件。

## 后续范围仍保留

开放式动态策划与创作对话、预览/导出转场一致性及全功能路线后续批次继续推进。本合同第一轮修复通过只证明对应行为，不等于整个目标完成，也不删除旧页面。

## 2026-11-05 第一轮结果

- 合同1–5已落实：原文件去重与分析版本、当前录像搜索、独立取景区间、短事件建议上下文、区间预览停止/重播、缓冲暂停音轨、保存原因、下载文件名、免费本机默认。取景预算裁切及版本裁切均需保留原观察；替换镜头清除旧取景来源，保留的取景镜头通过同一证据边界校验。
- Sol/high发现并闭环三项P2：预算裁切丢观察、评分/提示用旧时长、替换继承旧provenance及后端不兼容。实际UI/FFmpeg与模拟媒体时钟测试分开，不冒称已完成真实音画质量人评。
- test-affected -Browser：1235 passed、2 skipped（.cache/j1-feedback-affected.xml）。verify：4719 passed、7 skipped、2 desktop fixture errors（.cache/j1-feedback-verify.log）；已定位继承PS7模块路径导致Windows PowerShell找不到Get-FileHash，build-desktop显式导入本机Utility模块后原两项桌面测试通过（.cache/j1-desktop-recheck.xml）。未再次重复整仓；Ruff格式/lint、mypy 193源文件、CLI help/version均通过。不得把原verify退出1写成整轮全绿。
- 真实素材浏览器核对在 http://127.0.0.1:8766/studio ，三个原文件、111事件、取景输入与源播放已验证，无页面脚本错误；截图 .cache/scratch/j1-feedback-live.png。自动审批拒绝终止8765旧服务，未绕过；另起8766服务。8765仍可能是旧路由/旧后端，应使用8766预览。
- 旧审计统计更正：37条并非真正零时长，而是1微秒，已更正审计。原事件/源/账本未改；没有新付费调用；语音暂用免费本机。J1真人结论保持未通过，不要求现在复测。

## 下一批（仍在当前目标内）

- 单video随机seek解码等待及即时预览转场与导出不一致仍需处理，见TD025。
- R3文本创作对话在独立工作树 .worktrees/creation-reasoning-core，有8个新文件（应用提案/协议、DeepSeek适配器、可信准备确认服务及各自测试），未集成主树/未接UI。Sol/high要求已修价目身份/完整上下文预留、v4祖先、坏usage保留身份、取消Outcome；最后发现真实load_chain在async execute里嵌套asyncio.run，需核对是否已to_thread并补真实链测试。所有模型测试为fake，不能记真实AI已验收。
- 实际文本AI调用需要独立费用确认；旧分析¥50与免费语音选择不授予新调用。无需为此停掉其他开发。

## 2026-11-05 R3核心检查点（尚非界面交付）

8个核心/适配器/服务及测试文件已集成主树。支持可信版本快照、纯文字模型协议、严格可执行编辑提案/澄清、过期检查、v4 manifest兼容、准备报价/单次明确API确认、OS锁幂等及不可覆盖调用记录。未接server/Studio UI，未授权/未发送真实模型请求；语音仍免费。

独立Sol/high发现的v4祖先、费用依据、坏usage调用身份、取消结果与async嵌套loop均已处理。最后一项补保留真实load_chain的CreationJobs回归。主树相关测试全通过，精确数量见.cache/reasoning-main.xml；Ruff格式/lint及mypy197源文件通过。未因该离线核心再重复23分钟整仓，不冒称新核心已通过整仓或真实AI质量验收。

下一步是可信服务的界面纵切片与动态方案；实际调用仍须独立确认，不能把旧分析授权当新文本发送许可。适配依据已核对 [DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/) 和 [官方中文价目](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)；不改旧价格/调用证据。未知实际模型或usage保留未知费用。

## 2026-11-05 R3界面里程碑

HTTP与Studio已接入：默认免费本地规则，显式切换AI后准备可信已保存版本的文字请求；展示实际请求与保守费用上限，勾选并逐次确认才发送。澄清不改镜头；提案先预览，再经后端核对job/plan/父回执和修订规则，应用后由用户保存。切项目/版本/模式或未保存修改使旧UI结果失效；已发送记录可在对应保存版本恢复，只读结果、不重新调用。刷新恢复所选方案，避免读错父版本。

7项真实浏览器回归使用真实HTTP/CreationJobs/修订链和明确fake模型传输；覆盖单次确认、失联后恢复、模式ABA、未保存修改、同文双请求恢复失败不残留旧提案。HTTP8项及服务/Studio定向合计40项通过。界面截图 `.cache/scratch/reasoning-ui-quote.png`、`reasoning-ui-proposal.png`；合成测试素材，不是实际AI质量证明。

完整 `scripts/verify.ps1`：4813 passed、7 skipped，1237.56秒；格式/lint/mypy198源文件和CLI烟测通过，日志 `.cache/reasoning-ui-verify.log`。没有真实模型或付费语音调用，未运行Release，J1人评仍未通过。

后续并行核心：`.worktrees/j1-preview-corrections`预加载在真实媒体槽位跨源复用失败，尚不可集成，TD025未完成；架构角色一次升级定位。`.worktrees/creation-reasoning-core`动态方案协议/本地编译已定向验证，等待独立身份审查，尚未接provider/service/UI。动态策划与剪辑提案分别绑定各自输入，不用旧EDL冒充新候选篮子。
