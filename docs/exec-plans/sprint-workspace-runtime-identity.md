# 启动器拒绝旧运行时

2026-11-07，延续R4及J1“新功能是否生效”的真实交付问题。旧同repo服务可能被复用而缺新路由，不能通过停止8765绕过既有自动审批拒绝。

## 合同与归属

决策见[ADR-005](../design-docs/adr-005-workspace-runtime-identity.md)。Astra/low只读设计，Sol/medium在preview树codex/workspace-runtime-identity-20261107实施，parent持文档/集成，唯一Sol/high查身份/进程/文件边界。实现仅runtime_identity.py、server health、start-workspace.ps1及对应测试，不改费用/Provider/原素材/账本。

服务启动时固定源码身份；启动器独立算预期并比较实际packageRoot/hash，保留原应用/PID/repository/owned helper判定。过时占用拒绝并提示新端口，不kill既有进程。包内链接目录不能越界读数据或递归循环。源码指纹按实际包布局兼容开发src与便携site-packages，不把共享editable另一checkout冒作当前代码。

## 当前证据

- 初版20项通过，parent复跑生成preview树`.cache/runtime-parent-final.xml`；涵盖真实新端口启动、相同PID复用、旧字段/错hash/错root保留原服务、JS/Py变更后health快照固定。
- guard及parent合成NTFS fixture发现P2：Path.rglob递归junction且子文件is_symlink为false，外部JSON修改影响源码hash。已改walk剪枝与读前canonical containment，包根祖先junction允许。
- 最终`.cache/runtime-junction-final.xml`：21通过、0失败/错误/跳过，54.813秒。parent原合成proof复核外部JSON变化不影响hash。Ruff/format/mypy两源通过；guard最终只读复核通过，未独立跑pytest。
- 尚未集成root或完整门禁，不提前合main。未操作8765/8769等用户既有服务；仅测试临时repo/空闲端口，原启动器的owned helper清理未改。
