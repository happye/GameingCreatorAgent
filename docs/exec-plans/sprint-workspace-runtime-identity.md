# 启动器拒绝旧运行时

2026-11-07，延续R4及J1“新功能是否生效”的真实交付问题。旧同repo服务可能被复用而缺新路由，不能通过停止8765绕过既有自动审批拒绝。

## 合同与归属

决策见[ADR-005](../design-docs/adr-005-workspace-runtime-identity.md)。Astra/low只读设计，Sol/medium在preview树codex/workspace-runtime-identity-20261107实施，parent持文档/集成，唯一Sol/high查身份/进程/文件边界。实现仅runtime_identity.py、server health、start-workspace.ps1及对应测试，不改费用/Provider/原素材/账本。

服务启动时固定源码身份；启动器独立算预期并比较实际packageRoot/hash，保留原应用/PID/repository/owned helper判定。过时占用拒绝并提示新端口，不kill既有进程。包内链接目录不能越界读数据或递归循环。源码指纹按实际包布局兼容开发src与便携site-packages，不把共享editable另一checkout冒作当前代码。

## 当前证据

- 初版20项通过，parent复跑生成preview树`.cache/runtime-parent-final.xml`；涵盖真实新端口启动、相同PID复用、旧字段/错hash/错root保留原服务、JS/Py变更后health快照固定。
- guard及parent合成NTFS fixture发现P2：Path.rglob递归junction且子文件is_symlink为false，外部JSON修改影响源码hash。已改walk剪枝与读前canonical containment，包根祖先junction允许。
- 最终`.cache/runtime-junction-final.xml`：21通过、0失败/错误/跳过，54.813秒。parent原合成proof复核外部JSON变化不影响hash。Ruff/format/mypy两源通过；guard最终只读复核通过，未独立跑pytest。
- root已无提交集成并通过21项（`.cache/runtime-root-integrated.xml`），待完整门禁，不提前合main。未操作8765/8769等用户既有服务；仅测试临时repo/空闲端口，原启动器的owned helper清理未改。
- 2026-11-07用户因额度不足要求暂停：独立分支711734f已推送，root保留无提交merge。完整验证session97268、日志`.cache/workspace-runtime-full-verify.log`仍运行；恢复先核结果，不将定向测试代替完整通过。即时字幕预览只读设计已返回，尚未实施。
- 额度恢复后核实首轮完整验证退出1：1失败/4999通过/7跳过、1456.26秒。唯一失败为`test_inspection_http.py`健康响应整对象断言遗漏新增runtimeIdentity；已补充当前checkout包根及源码hash预期，原capabilities/PID/repo/Host/Origin断言保持。相关测试复核及新完整门禁通过前不合main；首轮失败日志保留。
- 修复后相关42通过/1跳过、57.241秒（`.cache/runtime-health-contract.xml`），Ruff/format通过。新完整门禁session99097、`.cache/workspace-runtime-fixed-full-verify.log`运行中。实际仓库新端口8770启动PID28620，health包根/hash与当前源码匹配，重跑启动器复用同PID；Studio及图层/字幕编辑模块均200，`.cache/runtime-live-smoke.json`。未停止既有服务。首次手动探测误用/static路径404，改按实际/assets路由后通过，并非模块404产品回归。
- 最终session99097退出0：5000通过/7跳过、1716.69秒，格式/Ruff/mypy208源/CLI全部通过。临时实测服务PID28620核对本次启动身份后已清理，未停止用户旧服务；实现门禁完成，J1/J3人评与发布状态不变。
