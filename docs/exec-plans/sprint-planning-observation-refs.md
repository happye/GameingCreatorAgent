# Sprint: planning observation references

日期：2026-11-17
关联：R3 / P021 / P040

范围：仅5个策划文件，基线5b2516e；不动时钟、素材、manifest、账本、发送门、前端和历史付费输出。

验收：含mandatory_topics的新prepare使用plan-snapshot-v4 / plan-topics-v2 / plan-reasoning-prompt-v5 / plan-proposal-v4。候选按facts/tags原数组位置产生fact:1/tag:1编号表；shot只接受自身candidateId下实际存在的编号。编译恢复原topic/rationale/observationQuote投影，前端覆盖率契约保持。旧v1/v2/v3及prompt3/4的正文、序列化、指纹和逐字引用规则保持。存档按mapping/prompt版本重建，未知版本及project/snapshot/request身份变化拒绝。模型rationale仍限500字符；后台展开原文无额外500字符限制。

实现：with_topics默认v1供历史调用，prepare_plan显式v2；provider只追加(v5,v4)；v4复用原编译和后台fingerprint绑定/echo记录，原provider输出不改。

2026-11-17离线证据：独占树.cache/scratch/validate_offline.py及offline-evidence.json（均为可重建缓存，不入提交）。根.venv运行、sys.path指向本树，无模型调用、无pytest/verify。

- 根真实a4714856…准备记录，从原录像/SQLite只读重建成功，snapshotFingerprint=8ef1831c08a2a2df749677c486fc3b647ecad0ab4a03ce10a3249562ab16c74d；重建request逐字段等于原request，_current_plan严格核requestHash成功。
- git show 5b2516e的实现离线加载：旧v1/v2/v3请求正文完全一致，v3 prompt3/4均一致，with_topics旧序列化完全一致；原付费输出因补句号仍按verbatim错误拒绝。
- 首个真实候选全部fact/tag编号投影（v4RefsChecked=2）保持原文；另一候选独有fact:3、未知编号、坏proposal指纹和未知mapping版本拒绝。v4实际编译投影通过。
- 真实源v4内存prepared重建完全一致；改projectId、snapshotFingerprint、requestHash均拒绝；service错误echo仍采用后台绑定并记录mismatch。
- 受影响5文件Ruff通过；mypy通过（5 source files）。未安装依赖，未改原数据，未commit/push。

主树集成：相同真实来源离线重建脚本通过（约2秒），旧请求/新引用投影/绑定及echo兼容保持。唯一task_quality_guard静态通过，无未闭合P1/P2。plan_reasoning_request为73行、refs helper为16行。

限制：新提示尚无付费效果验收；旧失败记录不重标、不重发。未运行pytest或完整检查。

重启主树8766服务后，实际POST prepare_plan返回638e58480516d250009309f5231989dfe58dbbc689b7e422886ad217081af728，plan-snapshot-v4/plan-topics-v2及首个候选fact:1、fact:2已生效；只准备，未调用模型。原文保存在真实操作目录planning-refs-prepared-only.json。
