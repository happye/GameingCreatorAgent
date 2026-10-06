# 受控描述条件草稿 Worker

2026-10-06；owner detail_cost_history 接续；独立 `.worktrees/detail-query-draft` / `codex/detail-query-draft`，基线4a84c40。

独占新 Application `detail_query_draft.py`、`test_detail_query_draft.py` 和本文。root 负责 POST、页面、共同记录和集成；旧 cost 工作树冻结。本任务没有 Provider、HTTP、数据库、文件写入或费用行为。

## 给用户的作用与下一步

用户输入“白发、红色外套、拿着蓝色扁平物体”，可以得到有明确衣物/持有物归属的可编辑条件，减少手工添加条件。名字、技能或修饰词认不出来时，原文字仍在草稿里；否定、“或者”、多个人物或先后动作不能偷偷变成肯定 AND。下一步先做纯解析器和反例检查，再交 root 接入必须确认的页面；草稿不证明视频中真的存在相应内容。

## 接口与方案

`draft_detail_query(text: str) -> dict[str, object]` 返回七字段：`schemaVersion=actor-detail-query-draft-v1`、原样 `originalText`、`status=ready/needs_review/unsupported`、`spanOffsetUnit=unicode-code-point`、冻结 query-v1 `constraint` 或 null、`spans` 和 `unparsed`。

每个 span 为 `start/end/text/kind/reason`，kind 是 recognized/connector/unparsed，reason 为可显示的中文说明。spans 顺序完整覆盖原句，每段非空、不重叠；unparsed 是其中未处理片段。偏移是 Python Unicode code points，页面只显示 text，不用 JavaScript UTF-16 重切。输入非 str 或超过2048字符抛 ValueError，不能截断；空句不能 ready。

先冻结有限中英文颜色＋头发、颜色＋衣物、持有物、动作/效果和环境短语；每个值经已有 `normalize_attribute_value` 核验。不取私有词表，不扩大 domain vocabulary。完整短语优先，英文词有边界，不在未知词内部搜子串。衣物短语的颜色/形状同 `clothing1..16`；不同衣物或物品分别分组 `held1..16`，发色 hair，其他沿用 action/effect/environment。

逐字符 accounting 保留空白、标点和未知片段。只允许有上下文意义的同主体/查询前缀/AND连接词，不能把任意动词或名字当 filler。重复条件明确留待核对；互斥同部件条件同样不能直接 ready。否定、OR、多主体、关系、时序或总条件数超过16时，constraint=null，不给可能歪曲原义的子集草稿。只有环境无法构成冻结 QueryConstraint；已有 actor 条件但未知词存在时，needs_review 可提供待明确确认的子集。

## 实施前自审

- 普通正向短句才可全量 ready，未知词不能因为其附近有已知关键词就消失。
- 衣物颜色不能跨未知名词或标点随意绑定，未知颜色不能被替换为默认颜色。
- 重复条件和衣物数量不能无声归并；条件超限不能取前16项。
- 关系/时序只支持显式拒绝，不能用现有同主体 AND 假装完成复杂句法。
- 用户自行确认仍是后续页面动作；此函数不运行 matcher、不产生验收通过，也不改变旧模型结果或人评门槛。

## 当前检查点

已读取 AGENTS、HANDOFF、query-v1、主体规格、Phase0 与原方案；开始时工作树干净，init -CheckOnly 通过11项。接口已通知 root。

## 已实现与实际验证

用户现在可以把有限正向中英文描述转换成草稿，例如“白发、穿着红色外套，手持蓝色扁平物体”生成发色、同衣物的颜色/形状，以及持有物形状；“红外套和蓝围巾”分属不同衣物组。“恶魔领主”“释放某技能”、emoji 或 HTML 样式文字会留在未处理区，不能被当 filler 消失。“白发或黑发”“两个白发角色”“先抬头再跳跃”等明确不给肯定manifest。原句和各片段完整保留，草稿本身不执行检索或匹配。

新增 **106 项**有意义回归：有限中英文形式、同衣物颜色/形状、多部件独立组、动作/效果/环境别名、环境-only、未知名字/技能/颜色/复杂词/安全文本、否定/OR/多主体/关系/时序、重复和互斥、组合16项边界、Unicode code points/emoji组合、原句完整accounting、输入边界及重复调用独立性。每个输入都核验spans无间隙/不重叠、原文拼接一致，所有输出值可以加载冻结query-v1且没有新增词表值。

先 dot-source 根 `scripts/env.ps1`，用 root `.venv/Scripts/python.exe -B`、own `src` PYTHONPATH，预建独立 `.cache/draft-runs` 和 pytest cache；Ruff/mypy 也使用 own cache，无安装或全局设置。最终命令：

```powershell
G:\Tools\ChatGPTRepo\GameingCreatorAgent\.venv\Scripts\python.exe -B -m pytest tests/test_detail_query_draft.py tests/test_detail_query.py tests/test_actor_detail_matching.py tests/test_architecture.py --basetemp=.cache/draft-runs/regression -o cache_dir=.cache/draft-pytest-cache --tb=short -W error
```

结果 **146 passed / 0 skip，1.88s，警告作为错误**。Ruff格式/lint两个own Python文件通过，Application模块 strict mypy 通过。

首轮104/106通过，发现英语“on a stone platform”的冠词以及“white hair and one red-haired person”第二主体提示两处有限语法遗漏；已补明确规则，不用通配丢词。mypy字典声明和首轮pytest cache父目录准备已修复；上方最终联合检查无警告。没有HTTP、Provider或费用，没写真实侧车/账本、源数据，也没改旧cost worktree。

## 剩余限制与具体交接

这不是通用语言理解器。姓名、技能、未知修饰、未知颜色及其他自由语法仍需人工编辑；语法只在有明确覆盖的正向同主体短句上ready。重复/互斥保留第一次已识别条件并明确needs_review，用户必须确认只核对这一部分，不能据子集结果宣称整句满足。超过16项不给前16项manifest，超过2048字符直接ValueError，不截断输入。v4视觉理解和F006/F009/F010质量门槛未改变。

已向root说明结果、使用帮助、反例证据和限制。下一步root集成纯POST与页面确认/未处理提示，检查迟到响应和部分确认流程，再执行本切片完整verify；本worker提交仅owned三文件后冻结，不接触server/UI或公共交接。真实v4新对照仍只冻结方案，不发送已有次数用完的请求。
