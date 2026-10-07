# Phase 0 跨素材联合检索

2026-10-07，root / Codex，codex/visual-details，接0a85f3a。上一goal turn为progress：批量准备已提交、真实三录像／恢复证据齐备；goal继续active，旧worker／worktree冻结。

F005主交付：同一查询在明确选择的多个Completed任务中建立一个联合语料，BM25／E5／RRF统一排名；不是各任务TopK拼接或比较不同语料的原分数。每项保留原runId／mediaId／候选ID、源区间、证据、原facts与uncertainty。不把不同录像相同时间／描述去重，不重复选择同源的不同分析版本，原单run排名／候选ID／SQL合同与benchmark保持。

root独占application/retrieval.py共同排名内核与跨素材结果、cli/main.py新search-project组合、Infrastructure项目内独立查询文件记录、scripts/search-project.ps1、针对性行为与真实已完成任务验证，规格／指南／公共交接。最多100个显式run ID，输入与所有素材完整核验先于本地模型；读取SQLite不写基础表，不恢复未完成任务。结果按独立schema/version保存在新项目查询目录，保留scope身份与来源；没有新SQL／HTTP合同，不碰工作台路由／静态资源。

验收：不同录像相同时段均保留、联合BM25／语义检索与单语料算法一致、同样输入顺序无关、原候选ID和事件归属、音频fallback、空查询／无候选、不完整／篡改／同源重复拒绝、原单任务回归、本地E5与实际三开发录像、另一进程读回来源及固定排名。0付费Provider／预留／真实人评，原unknown／待授权proposal／F006/F009/F010false保持。TD005／TD010／TD011／TD012／TD013继续延期，不因重复微修停主线。

已向用户说明本轮一次需求搜索多个已完成录像，保留原来源／时间／证据，不重新分析或付费。下一步先复用并验证联合排名内核，再接CLI及公开脚本与真实使用证据。

## 实现与实际使用

最终一次完整2157passed／1旧test_media_batch coverage状态保存失败／1 Windows symlink权限skip376.91s；JUnit2159／errors0、40新增全部通过。唯一旧失败storage.batch_checkpoint按TD012只窄复查一次1passed0.648s，保留原失败、不称首轮全过／不重跑无变化整套。161格式／84类型／lint、后续CLI／双离线wheel均通过，SHAde10d6cedda89407d814943938502460ace0b824c6f65029ff8b135f2d8780be，83包文件逐字节同源码且无媒体／环境／缓存／DB。回执.cache/project-retrieval-tests.xml／verify.log／old-failure.xml／package.json；新40行为和原候选／归属／单run合同通过。

共用_search_documents保留原单run校验／BM25／E5／RRF／拒判规则、候选clip-SHA24、文本／事件embedding身份及旧retrievalVersion。内部Document补原run／原文档身份，联合key带run前缀且_duplicate先比较media，不同源同区间不去重；search_timelines明确1–100源，重复run／SHA／media拒绝，排序与scope ID由真实来源／配置身份决定。单源联合候选与原搜索逐项完全相等，全局BM25和语义margin从联合语料计算，不拼单run前K。

CLI search-project先查参数及所有Completed来源完整性，再构造本地E5；SQLite全程read_only，不调用persist_search／recover／ASR／Vision／HTTP／预算。候选JSON共用旧序列化保持原facts和uncertainty，附runId／sourceName／源SHA，全局rank。project-search-v1／bm25-e5-rrf-v7-project-v1结果保留scope／源配置和管线，源核验与总查询时间；独占新目录result及最后fsync SHA回执、只读读回与边界检查。没有新SQL／HTTP合同，工作台不变。

40新增行为首次基础38全过，补全局语义margin与取消后136定向71.203s全部通过（含原单run、long worker分批／存储和架构）。生产import重复直接去除、夹具lint直接格式化，不做局部调查。完整验证冻结后只更新文档／ignored证据，当前一次完整运行结果补记下方，不重复无变化整套。

真实三开发PV：角色移动词法449ms／本地hybrid3880ms，各Top10均含三源、221 embedding文本／78缓存／1本地worker batch；公开PowerShell7中文需求1153ms／相同scope与词法全排名，另一真实进程读回hybrid原来源／候选／区间／证据／分数／原不确定性／记录SHA一致。same-source v4/v6在构造embedding前拒绝，拒绝未添加文件。查询后基线838文件（含最初3条查询的6文件）逐字节保持，新增4查询8记录文件，原单run检索214→214、三源SHA不变，unknown¥4.065536／空retry命令和未授权proposal原SHA保持。

首次校验把长负面句预计为空而失败；实际返回1候选，逐文档tokens查明唯一共享“存在”（原描述“仍存在”），修正校验预期而未改生产检索，不抹去3真实记录。最终又显式4次检索，总7项目查询／14记录文件；当前报告保存最终4次证据，早期3目录仍在原项目。TD004记录负面／整句边界，不称“没有素材”或“负面通过”，F006/F009/F010false。0付费Provider／新预留／人評，E5 CPU／硬件成本未测、正式独立质量仍待验收。

ignored artifacts/project-retrieval-validation/check-project-search.py／report.json／public.stdout.json／stderr为本机证据；主报告含实际四查询ID／原排名／scope／embedding及读回标记。只读旧未知与新proposal、原filebyte由真实脚本核对；未提交录像／DB／查询结果。当前仍CLI／PS入口，未重新部署UI或新增网页路由。

已向用户详细解释三源一次查、来源／相同时间独立保留、真实0.45秒3.9秒、读回相同、负面1候选和延期处理；下一root主线现有本地工作台的多来源选择／联合搜索与按源回看，先登记归属，保留来源边界和原篮／导出顺序。旧worker与小问题延期，付费两候选仍待授权，goal active。
