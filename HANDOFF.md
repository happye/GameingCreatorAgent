# HANDOFF（覆盖快照）

读 **STATUS.md** 作唯一当前状态；本文件只作短接手摘要。历史流水已删除（见 git／progress.md）。

## 现在能做什么
- 本机：录像准备→语义时间线→自然语言检索→创作方案／渲染／旁白／字幕／发布包检查（demo-phase0 等已有端到端证据）
- 离线债持续打磨中；**未**宣称 F006／F009／F010 或 TD004／TD009 关单

## 边界（未授权勿做）
付费视觉、新下载、真发布、支付／订阅、云端上传、代选 A／B／D、把人评标成通过。

## 费用与冻结
- 月度预授权 ¥50：仅用户指定素材分析；超支单次再问；硬发送门禁保留
- **冻结** P046–P051、P038 直至首个模式完成人评

## 环境
Windows PowerShell：. ./scripts/env.ps1；Python -B；pytest 用 --basetemp .cache/pt-<name> 并删除。推送可用 Clash 127.0.0.1:7890 + HTTP/1.1，不 force。Codex 仅维护**已提交**的 9 个 .codex/agents（勿提交未跟踪 gc-*）。

## 缓存
.cache 可重建。一次性脚本放 **.cache/scratch/**，会话结束可删。勿删 models／付费证据／用户创作。erify.ps1 与 pytest 应自行清临时目录。

## 下一步
见 STATUS.md「下一步」。并行写者才用 .worktrees/，集成后退役。分支／worktree 打包删除留给后续步骤。
