# HANDOFF（覆盖快照）

以 **STATUS.md** 作唯一当前状态；本文件只作短接手摘要。

## 现在能做什么
- 本机：录像准备→语义时间线→自然语言检索→创作方案／渲染／旁白／字幕／发布包检查
- 离线债可打磨；**勿**宣称 F006／F009／F010 或 TD004／TD009 关单
- `python -B scripts/status.py` 只读打印进度数字

## 边界（未授权勿做）
付费视觉、新下载、真发布、支付／订阅、云端上传、代替 A／B／D、把人评标成通过。

## 费用与冻结
- 月度预授权 ¥50：仅用户指定素材分析；超支单次再问；硬发送门禁保留
- **冻结** P046–P051、P038 直至首个模式完成人评

## 环境
Windows PowerShell；`. ./scripts/env.ps1`；Python `-B`；pytest 用 `--basetemp .cache/pt-<name>` 并删除。推送：Clash `127.0.0.1:7890` + HTTP/1.1（可设 `http.proxy`/`https.proxy`，清 `NO_PROXY`），不 force。Codex 仅维护已提交的 9 个 agents。

## 缓存与分支
`.cache/scratch/` 可删。本地 78 条快照分支已 bundle 到 `.cache/scratch/step2-local-branches-*.bundle` 后删除；清单见 `docs/archive/step2-branch-bundle-inventory.md`。过期 handoff／10 月报告在 `docs/archive/`。

## 下一步
见 STATUS.md。并行写者才建 `.worktrees/`，集成后退役。
