# Sprint：TD004 残余误召回 — 射击代理 chrome／汽修域错配／纯语义动作门闩

**状态（2026-11-01）：已完成（TD004 仍 open）。**

## 选定

继续 **TD004**（相对 TD009 ROI 更高）：

- demo-phase0 无射击／汽修正向语料；合成夹具可复现：`shooting` 在 **pure semantic** 下仍会抬起「拿枪／爆炸特效」；`汽车维修` 词法会命中「飞船维修」。
- hybrid 对无词法锚点已有 `semantic_ambiguity_without_lexical_anchor`；纯语义与汽修域错配仍漏。

## 非目标

- 不关 TD004／TD009／F006／F009／F010
- 不付费视觉、不发明伪 demo 语料、不代选 A／B／D

## 设计

1. **射击代理噪声**：shoot 查询下，positive_text 无射击动作词、仅有持枪／爆炸等代理描述 → 排除（全模式，含 semantic）。
2. **汽修域门闩**：查询含汽车／车辆／发动机等且含维修／修理／拆卸时，文档仅有维修语义但无汽车域词 → 排除。
3. **纯语义动作门闩**：action 查询的 semantic 分只保留 positive_text 含该动作证据的候选（防 EqualSimilarity 抬起无关片）。
4. demo-phase0 只读：射击查询仍空／abstain（缺库 skip）。

## 验收

- [x] sprint
- [x] 实现 + 合成／demo 测试
- [x] 文档；债务仍 open


## 结果

- `_shoot_proxy_noise_documents`：持枪／爆炸特效无射击动作词则排除；shoot 别名补开火／fired
- `_automotive_repair_mismatch_documents`：汽车域查询不命中纯飞船／装置维修
- semantic（含 hybrid 语义通道）动作查询须 positive_text 含动作证据
- demo-phase0 只读：射击空召回＋汽修查询空
- **不宣称** TD004／F006 关单
