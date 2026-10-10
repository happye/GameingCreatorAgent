# Codex子Agent按能力分工

用户于2026-10-11要求参考个人及投资项目的Claude Agent，把子任务分给合适模型以节省额度。这里使用Codex原生配置，并保留当前聊天可立即执行的明确模型分配方式。

| 任务 | 角色 | 模型／推理 | 边界 |
| --- | --- | --- | --- |
| 查文件、入口、调用链 | task_explorer | gpt-6-luna／high | 只读定位，短结论和文件依据 |
| 看指定任务的进度 | task_progress_monitor | gpt-6-luna／low | 只读真实句柄／日志，不重启、不编进度 |
| 落实已确认开发方案 | task_developer | gpt-6.1-sol／medium | 明确文件归属，做必要验证 |
| 一般代码审查 | task_reviewer | gpt-6.1-sol／medium | 只读，有触发证据才报问题 |
| 费用／持久化／并发等关键审查 | task_quality_guard | gpt-6.1-sol／high | 一次重点审查，不和普通审查重复 |
| 复杂跨模块设计与权衡 | task_architect | gpt-6-astra／low | 只读设计，已有方案不重新设计 |

默认未指定模型的子Agent为Luna／medium，最多同时三个子Agent，不含主Agent；主模型及其推理设置保持用户原选择。简单一步操作仍由主Agent完成，不为了并行而增加Agent；多Agent本身会增加token，节省额度的实际幅度未经对照测量。

## 配置位置及官方依据

项目原生配置为`.codex/config.toml`和`.codex/agents/task_*.toml`；个人配置已安装到`C:/Users/Crux/.codex/agents/`，个人config.toml新增agents默认项，原模型及其他配置保持。原配置备份路径记在ignored `.cache/codex-agent-routing-installation.json`，备份留在个人Codex目录，不提交凭据。项目源码不依赖个人绝对路径；其他机器可用`./scripts/install-codex-agents.ps1`安装，目标已有不一致配置时拒绝静默覆盖。

[官方子Agent说明](https://learn.chatgpt.com/docs/agent-configuration/subagents)明确支持个人／项目agents目录的独立TOML，每个角色包含name、description、developer_instructions，并可设model／model_reasoning_effort／sandbox_mode；[官方配置参考](https://learn.chatgpt.com/docs/config-file/config-reference)支持agents.enabled、default_subagent_model、default_subagent_reasoning_effort和max_concurrent_threads_per_session。这里只使用上述设置，不复制Claude的model别名或Read/Grep工具列表。角色文件设置可覆盖明确spawn设置；父会话的实时权限设置也会重新应用，不能把read-only配置误报为当前任何权限下都强制只读。

## 当前会话如何立即使用

当前聊天已注册的角色清单不会因为写入文件立即刷新；本次尝试task_explorer得到unknown agent_type，保存证据，不重复尝试。当前会话可用已存在的default／worker类型，明确传model和reasoning_effort，fork_turns=none并把对应角色指令／必要路径写入message。模型覆盖时不要fork整个历史：本会话工具会让全历史fork继承主模型。写任务仍须明确owner、告知不是唯一开发者；不用固定绑定第三方模型的旧designer／reviewer来假装执行新策略。

按官方机制，新会话可加载角色文件后按角色名委派，例如“请用task_explorer定位这个入口”。本次独立CLI真实验证在同一进程经历网络断流后退出0，创建并完成一个task_progress_monitor只读子任务；这是新会话验证，不称原聊天角色清单已热刷新。个人及项目配置为后续创建的子Agent提供模型与职责，当前聊天的明确模型分配已经实际验证，可立即使用。配置不改变已运行旧子Agent，也不自动重启App或恢复视频分析。

## 实际验证与适用范围

本机原生codex-cli 0.162.0-alpha.17.2使用strict-config成功读取默认Luna／medium、并发3、主模型仍gpt-6.1-sol。三次真实子任务分别用Luna／high、Sol／medium、Astra／low完成定位、审查和设计约束核对；只读执行数据库及turn_context核对型号／推理，没有模型重路由。六份TOML与个人安装副本逐字节核对，报告在ignored artifacts/codex-agent-routing-validation/。

debug prompt-input输出未包含自定义角色目录，不能据此证明角色注册或不支持；原失败回执保留。独立CLI派发只启动一次，原transport自行断流重试后成功结束，本任务没有重新启动该验证；CLI使用ephemeral，其子任务没有持久化型号记录，具体三种型号的执行验证来自当前聊天的三份独立记录。需要新名字无法解析时按上方明确模型方式处理，不能静默用错型号；实际新名字派发成功后再更新此项证据。

模型可用性以当前工具及实际运行结果为准，不保证未来账号一直可用；配置选择不代表内容质量验收。本次没有DeepSeek调用／新录像分析／费用预留，F006/F009/F010false。项目仍按原交接暂停，只有用户恢复才继续视频项目开发。
