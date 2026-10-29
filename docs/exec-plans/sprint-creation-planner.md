# R1 首切片：真实保存素材→创作方案→剪辑决策

2026-10-30，用户批准全产品并行实现，架构师task_architect/Astra low裁定，主控落盘。开发前置不再是F006真人质量通过；不放宽原Completed、原始证据、费用和人工判断要求。

owner：task_developer/Sol medium在独立worktree .cache/worktrees/creation-planner-20261030，拥有新增domain/creation.py、application/creative_planner.py、application/edit_decision.py、infrastructure/creation_files.py、cli/creation.py、cli/main.py必要注册、scripts/plan-creation.ps1和新tests/test_creation_planner.py。主控拥有公共文档及feature_list；写者不是唯一开发者，不回退别人的修改，不递归派发。

用户效果：显式Brief JSON与项目内Completed run清单/已选事件→三种不同结构的模板创作方案、来源绑定的脚本草稿、缺口→按显式选择生成有效EditDecision。公开命令plan-creation，PowerShell包装脚本可运行。首步明确为离线模板规划，不冒称通用自然语言AI或人评通过；证据不足不能复制事件凑方案或编造事实。

合同：复用原MediaAsset/SourceRange/Store只读加载与完整性校验；每个EDL片段绑定原media SHA/run/event及有效源微秒区间，记录输出帧率和顺序，输出顺序按方案而不是源时间排序；三模板结构确有差异，时长不超Brief预算，缺主题明示缺口、不凭空生成得分。复用既有结构化描述，仅作可编辑脚本草稿。独占新输出版本目录、最后写回执，原项目/媒体/旧输出不改；无网络/下载/模型/新费用。输入严格拒绝越界、未知run/event、重复或跨源身份冒用；无完整方案时诚实返回不足，不能造三份成功。

必要验证：三结构差异/时长预算/源绑定、缺素材/缺主题、越界与错误来源、重复输出拒绝/重读一致、公开CLI真实Completed演示素材走通；Ruff与受影响mypy。不重复全量、禁止共享主venv uv写入；只读共享Python须先主树env、-B，设置隔离worktree PYTHONPATH与独立pytest缓存。实现后由独立关键边界评估者审来源/新文件发布，主控集成后一次定向验证。

下一切片：同一EDL接真实本地FFmpeg渲染MP4、验证片段顺序/时长/音画及原源不变。当前JSON方案不能计为渲染或端到端视频完工。自然语言Brief、可核实素材评分、配音/音乐、UI编辑等按全功能路线接续，不用占位接口或未连通页面计完工。

交付证据（2026-10-30）：8个源/入口/测试文件已主树集成；18项行为测试通过，Ruff和worker受影响mypy通过。Sol/high唯一独立评估PASS；3个P2已直接修复（同源同区间去重、时间序基线、零帧候选先过滤）。主树公开PowerShell脚本对demo-phase0的96b5f01530ce43e2944828fb0520b9b4成功输出，另进程逐文件SHA核对回执及38段hook-first EDL；本机.cache/planner-main-latest.json与planner-integrated.xml。无模型请求/新费用；尚未渲染MP4。仅P019/P021/P027记部分，其余模板库/脚本/缺口等独立功能不因基础草稿就升状态。下一切片合同sprint-creation-render.md。
