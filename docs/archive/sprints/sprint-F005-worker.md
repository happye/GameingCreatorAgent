# F005 检索 worker 检查点

日期：2026-10-04，Asia/Hong_Kong。Owner：Codex `demo_retrieval`，工作树 `.worktrees/demo-retrieval`。公共 CLI、依赖、SQLite 和交接由 root 集成。

## 当前实现

- `application/retrieval.py` 提供 `search_timeline`，lexical/BM25、semantic/cosine、hybrid/RRF；返回源区间、候选 ID、事件 ID、证据、事实和可解释排序信号。
- Completed 状态、run/media/duration/evidence 关联检查；词法中英基线；重叠且事实相近事件去重。ASR 为视觉事件补充文本；未覆盖语音可返回独立音频候选，不编造视觉事件。不填满十个结果。
- `LocalEmbeddingProvider.from_manifest(repository)` 使用固定 E5 ONNX、CPU、query/passage 前缀、attention-mask mean pooling、L2。原生库固定校验和来源检查；独立 worker 经 Windows Job/取消/超时回收。缓存含全部向量空间身份和文本 hash，坏缓存重算、坏模型拒绝，无联网回退。`use_cache=False` 可测无向量缓存冷运行，不读写共享向量缓存。
- 固定官方 Xenova export commit `761b726dd34fb83930e26aab4e9ac3899aa1fa78`，5 文件合计135,392,183 bytes；下载工具只写项目 `.cache/models/multilingual-e5-small/<revision>`。root 已准备并校验真实权重，worker 用 root `.venv` 与资产完成真实本地推理。
- `SearchResult.event_embeddings` 导出全部验证后的事件向量，subject_id 映射真实 event_id，text_hash 保留带 passage 前缀的完整文本；query 和独立 transcript 向量仅留 artifact cache。SQLite 迁移3由 root 的另一 worker 所有。

## 验证与限制

最终 focused pytest：64 passed/0skip（0.78s，`-W error`，包括3架构测试）。Ruff 及 mypy 4个 owned 生产/脚本文件通过；root整体 verify、真实 Completed run 的 CLI/SQLite 接线尚由集成负责人验证。模型默认 cosine cutoff=0.80 和 semantic margin=0.02 是未校准的 demo 参数，不是可用率或概率；需真实冻结查询对照，人工 U10 尚未验证。F005/F006 不得因实现存在而标通过。

```powershell
. ../../scripts/env.ps1
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
../../.venv/Scripts/python.exe -B -m pytest tests/test_retrieval.py tests/test_local_embeddings.py tests/test_architecture.py -W error -o cache_dir=.cache/pytest-cache-demo-retrieval --basetemp=.cache/pytest-demo-retrieval-6
```

### 真实模型对照与失败保留

报告均为 **developer text fixture / real local model**，不是人工视频 benchmark；位置在 worker ignored `.cache/`，root可复制至统一 artifacts 目录。

- `f005-real-bilingual-model.json`：最初8文本冷1807ms、热122ms；中文/英文改写top1正确，但中文太空激光负例得分0.84–0.856，cosine绝对阈值错返。
- `f005-real-retrieval-fixture.json`：初次3查询×lexical/semantic/hybrid完整对照；默认hybrid无词法锚点时加不同描述top分差保护，负例拒答，但正例低排名仍有无关尾部。
- `f005-real-retrieval-final.json`：加 relative best−margin 截断后，发现动态量化 batch上下文使冷/热向量稍有不同；该报告保留失败检查，不覆盖。
- `f005-real-retrieval-batch1.json`：最终 `local-e5-onnx-v2` 固定逐文本batch=1，space scope加入batch/inference版本，旧缓存自动隔离。无向量缓存冷三查询1868/1653/1667ms，显式prime后热110/111/109ms，每次6/6cache。冷/热 candidates（包括score/why）完全相同；中文仅jump、英文仅build、负例空。相关CRT均从项目 `.tools` 或 `.venv` 加载。

Hybrid 语义候选须同时满足绝对cutoff和距最高分不超过margin；词法结果独立保留。缺词法锚点时，不同描述top分差过小拒答；单一描述须cosine≥0.90。重复相同描述不同独立时间在门控时归一描述组，排名时仍分别保留。`semantic` 模式保留原cosine baseline供对照。上述保护在开发fixture上改进，不保证实际游戏查询无误报。

### 冻结与集成

所有8个 owned 文件已就绪且本 worker 冻结：`application/retrieval.py`、`infrastructure/local_embeddings.py`、`infrastructure/embedding_worker.py`、`tests/test_retrieval.py`、`tests/test_local_embeddings.py`、`scripts/prepare-embedding-assets.py`、`docs/references/embedding-model.json`、本 sprint。未改公共 schema/store/CLI/依赖文件，未发付费请求。

官方实现依据：[E5 原模型说明](https://huggingface.co/intfloat/multilingual-e5-small)、[固定导出文件](https://huggingface.co/Xenova/multilingual-e5-small/tree/761b726dd34fb83930e26aab4e9ac3899aa1fa78)。量化影响应在实际中文与英文检索对照中记录，不借原模型论文成绩充当本项目成绩。

下一步：root集成这些文件，按默认hybrid和显式lexical/semantic接CLI，持久化返回的事件向量与检索记录；对真实Completed timeline复验空结果/证据/JSON及整体verify。F006人工标签仍缺，不能用本轮开发文本判定U10门槛。
