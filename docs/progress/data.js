window.PROGRESS_DATA = {
 "schemaVersion": 1,
 "nodesUpdated": "2026-11-11",
 "groups": {
  "A": "基础架构与本地处理",
  "B": "视频理解与检索",
  "C": "创作规划",
  "D": "成片制作",
  "E": "多平台与发布",
  "F": "产品形态与交互",
  "G": "内容模式",
  "H": "商业化"
 },
 "summary": {
  "planned": 51,
  "delivery": {
   "delivered": 10,
   "partial": 41
  },
  "pct": 59.8,
  "first": 22,
  "firstDelivery": {
   "partial": 22
  },
  "firstPct": 50.0,
  "qualityAccepted": 0,
  "released": 0,
  "phase0Pass": 8,
  "phase0Total": 11,
  "td": {
   "resolved": 20,
   "partial": 3,
   "open": 5
  },
  "tdTotal": 28,
  "humanPending": 10,
  "journeyAgentPass": 3,
  "journeyHumanUsable": 0,
  "journeyTotal": 3
 },
 "journeys": [
  {
   "id": "J1",
   "name": "玩法展示：本地录像 → 约1分钟可发布成片",
   "steps": "导入录像 → 已有分析/检索 → 选玩法展示模板 → 渲染MP4 → 封面文案与B站发布包",
   "agent_run": {
    "date": "2026-11-11",
    "result": "pass",
    "evidence": "Claude Code 在 http://127.0.0.1:8791/studio 用真实录像《漫画群星：大集结》（artifacts/demo-phase0）走完新 Studio 全流程：一句话需求→填入→本地模板方案（推荐方案30秒、20个镜头）→导出MP4约30秒（预计29秒）→去发布→保存文案与封面→B站平台包约10秒，本地检查通过（官方规则与素材权利未核）。全程无付费调用。人评仍以 human_check 为准。"
   },
   "human_check": {
    "date": "2026-11-04",
    "verdict": "not_usable",
    "minutes": null,
    "interventions": null,
    "evidence": "第四次试用（新工作台全流程）用户提交七组反馈：跨游戏短事件混搜、素材来源不明、模板方案与规则助手能力不足、切镜卡顿/BGM重复、保存灰、平台包下载true.txt。本轮全流程未通过；不是重新否定第三次初稿观感。代码及运行数据核查见 docs/exec-plans/j1-fourth-trial-audit.md；当前Chromium复用既有包下载成功，未复现用户下载故障。用时及干预次数未提供。此前第三次（2026-11-03）两三分钟、未修改，用户评价“初版过得去”；原反馈仍保留在STATUS/HANDOFF和本报告。"
   },
   "unlocks": "冻结项 P038、P046–P051（2026-11-03 已由用户确认解冻）"
  },
  {
   "id": "J2",
   "name": "一句话找片段：Top-10 中可用 ≥70%",
   "steps": "选已完成录像 → 输入一句话查询 → 看前10名并逐个打分",
   "agent_run": {
    "date": "2026-10-07",
    "result": "pass",
    "evidence": "feature_list.json F005/F007 passes=true（commit 24ded10 起）"
   },
   "human_check": {
    "date": null,
    "verdict": "not_done",
    "minutes": null,
    "interventions": null,
    "evidence": "F006 仍为 false；progress-board §3 真实步骤 0/8"
   },
   "unlocks": "F006 / Phase 0 质量结论"
  },
  {
   "id": "J3",
   "name": "安装：便携包安装后启动工作台",
   "steps": "build-app → install-app → 启动 GamingCreator.exe → 工作台可用 → 卸载",
   "agent_run": {
    "date": "2026-11-01",
    "result": "pass",
    "evidence": "feature_list.json P039 implementation_evidence（install-app -Smoke 安装/升级/卸载）"
   },
   "human_check": {
    "date": null,
    "verdict": "not_done",
    "minutes": null,
    "interventions": null,
    "evidence": null
   },
   "unlocks": "对外分发（另需许可证缺口处理）"
  }
 ],
 "features": [
  {
   "id": "P001",
   "group": "A",
   "name": "本地媒体处理（FFmpeg 抽帧／音频，含 MKV/WebM）",
   "first": false,
   "delivery": "delivered",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [],
   "done": "可用FFmpeg从本地录像（含MKV/WebM）抽帧、取音频，作为分析与成片的基础，已工程交付",
   "todo": "未单独做质量评估，未发布",
   "updated": "2026-10-07",
   "sprints": []
  },
  {
   "id": "P002",
   "group": "A",
   "name": "开发用 CLI（analyze／search 等）",
   "first": false,
   "delivery": "delivered",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [],
   "done": "开发用CLI可运行analyze、search等命令完成分析与检索，已工程交付",
   "todo": "未单独做质量评估，未发布",
   "updated": "2026-11-05",
   "sprints": []
  },
  {
   "id": "P003",
   "group": "A",
   "name": "可替换模型 Provider",
   "first": false,
   "delivery": "delivered",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [],
   "done": "模型Provider可替换；11-09起付费Provider原始输出在校验前留存（TD026），已合main",
   "todo": "真实付费调用应用校验失败原因待新证据；质量未评估",
   "updated": "2026-11-09",
   "sprints": [
    "sprint-paid-output-evidence"
   ]
  },
  {
   "id": "P004",
   "group": "A",
   "name": "Prompt 版本化",
   "first": false,
   "delivery": "delivered",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [],
   "done": "Prompt按版本记录，分析结果可追溯到所用提示词版本，已工程交付",
   "todo": "未单独做质量评估，未发布",
   "updated": "2026-10-04",
   "sprints": []
  },
  {
   "id": "P005",
   "group": "A",
   "name": "模型成本可观测（未知不写零）",
   "first": false,
   "delivery": "delivered",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [],
   "done": "模型调用费用写入账本，未知费用不记为零，已工程交付",
   "todo": "未单独做质量评估，未发布",
   "updated": "2026-10-07",
   "sprints": []
  },
  {
   "id": "P006",
   "group": "A",
   "name": "SQLite 持久化与中断恢复",
   "first": false,
   "delivery": "delivered",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [],
   "done": "分析状态存SQLite，任务中断后可恢复继续，已工程交付",
   "todo": "未单独做质量评估，未发布",
   "updated": "2026-10-25",
   "sprints": []
  },
  {
   "id": "P007",
   "group": "A",
   "name": "批量任务队列（多素材准备）",
   "first": false,
   "delivery": "delivered",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [],
   "done": "可一次排队准备多段本地录像，失败后可续跑，已工程交付",
   "todo": "未单独做质量评估，未发布",
   "updated": "2026-10-07",
   "sprints": []
  },
  {
   "id": "P008",
   "group": "A",
   "name": "缓存",
   "first": false,
   "delivery": "partial",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [
    "src/gamingcreator/infrastructure/render_limits.py",
    "scripts/cache-maintenance.py",
    "docs/exec-plans/sprint-cache-reclamation.md",
    "src/gamingcreator/infrastructure/window_segment_cache.py",
    "src/gamingcreator/application/analysis.py",
    "docs/archive/sprints/sprint-t17-window-segment-cache.md",
    "tests/test_window_segment_cache.py"
   ],
   "done": "窗口级片段缓存命中可跳过视觉调用；有渲染容量门、媒体回收、向量缓存和分析复用检查",
   "todo": "缓存整体仍为部分完成；准确率与人评不在本项，未发布",
   "updated": "2026-11-03",
   "sprints": [
    "sprint-cache-reclamation"
   ]
  },
  {
   "id": "P009",
   "group": "A",
   "name": "OCR",
   "first": false,
   "delivery": "partial",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [
    "2026-11-01: offline hard-case fixture catalog (tests/fixtures/ocr-hard-cases) synthesizes byte-capped PNGs for plain_control / low_contrast / stylized_title; regression smokes Windows OCR without claiming accuracy, human review, or F006; retrieval integration still open"
   ],
   "done": "工作台一键用Windows OCR识别画面文字，可点文字跳转、按词查找；有离线难例回归",
   "todo": "风格化标题读不出，准确率未人评，OCR结果未进入检索",
   "updated": "2026-11-01",
   "sprints": [
    "sprint-ocr-frames"
   ]
  },
  {
   "id": "P010",
   "group": "A",
   "name": "场景切分（scene detection）＋黑屏检测",
   "first": false,
   "delivery": "partial",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [
    "2026-11-01: expanded synthetic black-frame/hard-cut fixture catalog (tests/fixtures/shot-hard-cases) with byte-capped MP4 regression; workbench/report copy notes 抽检未人评; humanReviewed remains false; accuracy still not human-reviewed; no F006 claim"
   ],
   "done": "detect-shots本地检测镜头切换与黑场，有合成硬切/黑场夹具回归",
   "todo": "仅抽查2处，准确率未人评",
   "updated": "2026-11-01",
   "sprints": [
    "sprint-shot-boundaries"
   ]
  },
  {
   "id": "P011",
   "group": "A",
   "name": "代理文件（Proxy）",
   "first": false,
   "delivery": "partial",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [
    "2026-11-01: make-proxy builds/reuses a 360p low-bitrate editing proxy per source SHA with a duration-scaled byte budget (<=1 GiB) enforced by -fs and MediaOutputLimit, duration check, temp-dir build and full cleanup on failure; /api/media?proxy=1 serves it only while its receipt matches; real 54.7s recording 25.3MB -> 4.2MB proxy; player auto-switch not done",
    "2026-11-01: batch make-proxy queues many prepared/analyzed runs via CLI (--run repeat / --all-eligible), scripts/make-proxy.ps1 -AllEligible, POST /api/make-proxy-batch, and workbench tasks dialog; each item still uses single make_proxy byte budget/duration/temp-dir cleanup; same-SHA shared in batch; cleanup entry still open"
   ],
   "done": "可生成360p编辑代理（按时长限额），工作台可切换代理预览，CLI/API/工作台可批量生成",
   "todo": "代理清理入口未做，播放器尚不自动改用代理",
   "updated": "2026-11-01",
   "sprints": [
    "sprint-editing-proxy"
   ]
  },
  {
   "id": "P012",
   "group": "B",
   "name": "本地语音识别 ASR",
   "first": false,
   "delivery": "delivered",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [],
   "done": "本地语音识别可把录像语音转成文字，已工程交付",
   "todo": "本机ASR无词级时间戳；质量未单独评估，未发布",
   "updated": "2026-10-04",
   "sprints": []
  },
  {
   "id": "P013",
   "group": "B",
   "name": "视频语义时间线",
   "first": false,
   "delivery": "delivered",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [],
   "done": "录像可生成带时间点的语义时间线（F004），已工程交付",
   "todo": "未单独做质量评估，未发布",
   "updated": "2026-10-24",
   "sprints": []
  },
  {
   "id": "P014",
   "group": "B",
   "name": "自然语言语义检索",
   "first": false,
   "delivery": "delivered",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [],
   "done": "可用自然语言搜索录像片段（F005技术可用），11-03修复攻击标签回归",
   "todo": "检索质量依赖P015人工验收，尚未通过",
   "updated": "2026-11-03",
   "sprints": []
  },
  {
   "id": "P015",
   "group": "B",
   "name": "检索质量人工验收（Phase 0 门槛）",
   "first": true,
   "delivery": "partial",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [],
   "done": "Phase 0检索验收8步工具全部就绪（登记参考、固定排名、前十评分、门槛报告）",
   "todo": "真实执行0/8：需你登记素材与参考、批准付费分析、人工评分",
   "updated": "2026-10-27",
   "sprints": []
  },
  {
   "id": "P016",
   "group": "B",
   "name": "视觉多帧动作理解",
   "first": false,
   "delivery": "partial",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [],
   "done": "视觉多帧动作理解已实现（F009），可从多帧判断动作",
   "todo": "质量未验收，需人工评估",
   "updated": "2026-10-11",
   "sprints": []
  },
  {
   "id": "P017",
   "group": "B",
   "name": "人物／衣物／持有物细节",
   "first": false,
   "delivery": "partial",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [],
   "done": "人物、衣物、持有物细节识别与检索已实现（F010）",
   "todo": "质量未验收，需人工评估",
   "updated": "2026-10-24",
   "sprints": []
  },
  {
   "id": "P018",
   "group": "B",
   "name": "游戏知识层（Wiki／补丁说明／用户资料）",
   "first": false,
   "delivery": "partial",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [
    "2026-11-01: local game knowledge entries with source kind/label, content-addressed immutable files and replaces-based version history; text or local file input via the activity-rule readers; game-scoped keyword search with citations and insert-into-narration; HTTP and unit tests; no automatic planner citation or web crawling",
    "2026-11-01: local directory batch import for txt/md (optional screenshots/PDF via existing read_rule_source OCR); CLI import-knowledge, POST /api/knowledge-import, creation-page folder path; source labels include 目录导入 + filename; no network scraping; duplicate game+text skipped; auto planner citation and web crawl still open",
    "docs/exec-plans/sprint-game-knowledge.md",
    "docs/exec-plans/sprint-studio-narration-revision.md",
    "2026-11-08: Studio manages local knowledge and imports real PNG/PDF with OCR source warnings. Matched current knowledge is frozen into v2 planning requests/quotes and adopted citations; empty context retains v1. Fake transport and baseline-v1 disk compatibility verified; real AI and human quality remain unassessed."
   ],
   "done": "本机知识条目带出处和版本历史，可导入文本/目录/PNG/PDF，Studio策划引用；同游戏两版补丁说明逐行对比（已合main）",
   "todo": "联网抓取未做；真实AI引用与人评未做",
   "updated": "2026-11-09",
   "sprints": [
    "sprint-game-knowledge",
    "sprint-studio-narration-revision",
    "sprint-knowledge-version-compare"
   ]
  },
  {
   "id": "P019",
   "group": "C",
   "name": "Creative Brief：一句话需求→结构化需求",
   "first": true,
   "delivery": "partial",
   "impl": "partial",
   "quality": "template_draft_not_human_accepted",
   "release": "not_released",
   "remaining": "Natural-language understanding, full creative requirements and render/UI integration remain; this slice is structured-input offline template planning and source-bound EDL only.",
   "evidence": [
    "docs/exec-plans/sprint-creation-planner.md",
    "tests/test_creation_planner.py",
    "scripts/plan-creation.ps1",
    "docs/exec-plans/sprint-creation-workspace.md",
    "tests/test_creation_jobs.py",
    "tests/test_creation_workspace_browser.py"
   ],
   "done": "一句话需求按本机规则识别游戏/时长/类型/平台/必须主题/排除/观众，确认后填入；结构化需求离线生成模板方案，可带入活动规则与本地知识",
   "todo": "规则覆盖之外的说法需手填；完整创意需求未覆盖；未经人工验收",
   "updated": "2026-11-10",
   "sprints": [
    "sprint-creation-planner",
    "sprint-creation-workspace",
    "sprint-j1-creation-usability"
   ]
  },
  {
   "id": "P020",
   "group": "C",
   "name": "活动规则解析（文本／网页／截图／PDF）",
   "first": true,
   "delivery": "partial",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [
    "docs/exec-plans/sprint-activity-rules.md",
    "tests/test_studio_activity_rules_browser.py",
    "2026-11-08: Studio local activity-rule panel reuses the existing extraction API; citations, explicit application to the current brief, source/project/unmount stale-result isolation, and text-input topic round-trip verified by 12 real HTTP browser cases. No cloud calls, remote URL fetching or large editor dependency; existing OCR/PDF evidence reused, creative quality unreviewed.",
    "2026-11-01: offline activity-rule extraction (name, period, platforms, min/max duration, orientation, required topics, forbidden items) with exact source-line citations from pasted text or local txt/md/html, screenshots via Windows OCR and PDFs via Windows.Data.Pdf page rendering + OCR; one-click brief filling; real Windows screenshot/PDF tests pass; no network fetching or model understanding"
   ],
   "done": "粘贴文字、填写活动网页地址（只读该页一次，记录网址/时间/SHA-256）或本地txt/md/html/截图/PDF，离线提取规则带逐行出处；Studio确认后填入需求",
   "todo": "需登录或脚本渲染的网页读不到正文；规则提取与创意质量未人工评审",
   "updated": "2026-11-09",
   "sprints": [
    "sprint-activity-rules"
   ]
  },
  {
   "id": "P021",
   "group": "C",
   "name": "Creative Planner：多套视频方案",
   "first": true,
   "delivery": "partial",
   "impl": "partial",
   "quality": "template_draft_not_human_accepted",
   "release": "not_released",
   "remaining": "Natural-language understanding, full creative requirements and render/UI integration remain; this slice is structured-input offline template planning and source-bound EDL only.",
   "evidence": [
    "docs/exec-plans/sprint-creation-planner.md",
    "tests/test_creation_planner.py",
    "scripts/plan-creation.ps1",
    "docs/exec-plans/sprint-creation-workspace.md",
    "tests/test_creation_jobs.py",
    "tests/test_creation_workspace_browser.py"
   ],
   "done": "离线模板多套方案＋真实文本模型动态策划：3套方案已采用进Studio（任务4c857005），模型抄错指纹的问题已修",
   "todo": "方案质量未人评；每次新的模型调用需单独授权",
   "updated": "2026-11-09",
   "sprints": [
    "sprint-creation-planner",
    "sprint-creation-workspace",
    "sprint-j1-creation-usability"
   ]
  },
  {
   "id": "P022",
   "group": "C",
   "name": "视频结构模板（攻略／功能展示／广告／实况）",
   "first": true,
   "delivery": "partial",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [
    "2026-11-01: offline structure templates for feature showcase / guide / campaign (roles, duration weights, ~1.5s per shot cap) recommended first; generic plans byte-identical; 200 related tests; gc-reviewer PASS; ad/live templates and model-based structure not done"
   ],
   "done": "玩法展示/攻略/活动投稿离线结构模板（角色、时长权重、单镜头时长上限），方案列表首推",
   "todo": "基于模型的结构生成未做；模板创意效果未单独评估",
   "updated": "2026-11-01",
   "sprints": [
    "sprint-content-modes"
   ]
  },
  {
   "id": "P023",
   "group": "C",
   "name": "素材评分（需求匹配等加权）",
   "first": true,
   "delivery": "partial",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [
    "2026-11-01: explicit master-plan 8-dimension material score per candidate; only offline-measurable dimensions scored (topic match, fact/tag detail proxy, description novelty, usable length, uncertainty proxy) with coverage reported, visual/emotional/narrative unknown; modes pick by score; 164 related tests; real demo-phase0 plans scored 0.58-0.94"
   ],
   "done": "按总方案八维权重给候选素材打分，仅离线可测维度计分并报告覆盖率，方案按分数选片",
   "todo": "画面质量/情绪/叙事维度仍未知；评分准确性未人工评估",
   "updated": "2026-11-05",
   "sprints": [
    "sprint-material-scoring"
   ]
  },
  {
   "id": "P024",
   "group": "C",
   "name": "素材缺口发现",
   "first": true,
   "delivery": "partial",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [
    "2026-11-01: non-blocking plan advisories (too few clips, insufficient total footage, short output, single source, single-clip topic, unknown dimensions) with suggestions alongside existing blocking gaps; real demo-phase0 single-source advisory correct"
   ],
   "done": "方案附阻断缺口与提醒及补素材建议；主题缺口可一键跳到素材页并填好搜索词，挑片入篮后再生成方案",
   "todo": "缺口提示有效性未人工评估；画面层面的缺口判断未做",
   "updated": "2026-11-10",
   "sprints": [
    "sprint-material-scoring"
   ]
  },
  {
   "id": "P025",
   "group": "C",
   "name": "解说脚本生成",
   "first": true,
   "delivery": "partial",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [
    "2026-10-31: offline template narration draft from saved revision clip descriptions sized to the output clock (3.5 chars/s budget, evenly sampled clips, honest omitted count), GET narration-script API and workspace button feeding local narration; 11 new tests plus 113 related (.cache/narration-script.xml); real 12s plan produced a 36-character draft spanning first and last clips; quality not human-reviewed"
   ],
   "done": "按已保存镜头描述和成片时长离线生成解说模板草稿；Studio可结合本地知识修订旁白",
   "todo": "无模型生成解说；文案质量未人工评审",
   "updated": "2026-11-08",
   "sprints": [
    "sprint-narration-script"
   ]
  },
  {
   "id": "P026",
   "group": "C",
   "name": "配音／旁白合成",
   "first": false,
   "delivery": "partial",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [
    "2026-10-31 R2-I: local Windows SAPI narration asset jobs, preview, output-frame attachment with gain/ducking, inherit/remove/ancestor restore, three-way mix render; 165 targeted tests (.cache/narration-main.xml), real Huihui 5.688s voice located at 3.000s in a 360-frame MP4 (.cache/narration-real-render.json), Bilibili seven-file package from the narrated render; code-quality-guard PASS; voice license unknown",
    "docs/exec-plans/sprint-studio-narration-revision.md",
    "tests/test_studio_narration_revision_browser.py",
    "2026-11-08: Studio edits attached narration, restores per-asset local drafts and resynthesizes with free local voices into a new revision. Late results and asset-switch draft isolation verified; real WAV/MP4/7-file package chain uses explicit fake voice engine. Voice quality and human acceptance remain unassessed."
   ],
   "done": "本机Windows语音合成旁白，可试听、挂接成片时间、调音量/闪避；Studio可编辑并重合成为新版本",
   "todo": "本机声音授权未知；云端配音需付费单独批准；音质未人工评审",
   "updated": "2026-11-08",
   "sprints": [
    "sprint-local-narration",
    "sprint-studio-narration-revision"
   ]
  },
  {
   "id": "P027",
   "group": "C",
   "name": "Edit Decision（结构化剪辑决策）",
   "first": true,
   "delivery": "partial",
   "impl": "partial",
   "quality": "template_draft_not_human_accepted",
   "release": "not_released",
   "remaining": "Natural-language understanding, full creative requirements and render/UI integration remain; this slice is structured-input offline template planning and source-bound EDL only.",
   "evidence": [
    "docs/exec-plans/sprint-creation-planner.md",
    "tests/test_creation_planner.py",
    "scripts/plan-creation.ps1",
    "docs/exec-plans/sprint-creation-workspace.md",
    "tests/test_creation_jobs.py",
    "tests/test_creation_workspace_browser.py",
    "docs/exec-plans/sprint-creation-editing.md",
    "tests/test_creation_editing.py",
    "tests/test_creation_revision_jobs.py",
    "tests/test_creation_editing_browser.py",
    "docs/exec-plans/sprint-clip-replacements.md",
    "tests/test_clip_replacement_core.py",
    "tests/test_clip_replacement_jobs.py",
    "tests/test_clip_replacement_http.py",
    "tests/test_clip_replacement_browser.py"
   ],
   "done": "生成源绑定结构化剪辑决策（EDL），可保存版本、换镜头、调整并重开",
   "todo": "自然语言驱动剪辑决策未做；决策质量为模板草稿未验收",
   "updated": "2026-11-06",
   "sprints": [
    "sprint-creation-planner",
    "sprint-creation-editing",
    "sprint-clip-replacements"
   ]
  },
  {
   "id": "P028",
   "group": "D",
   "name": "本地渲染（裁剪／拼接／缩放／变速／音频／转场／编码→MP4）",
   "first": true,
   "delivery": "partial",
   "impl": "partial",
   "quality": "technical_render_tests_passed_creative_quality_unreviewed",
   "release": "not_released",
   "remaining": "Timed text/PNG layers now have source-bound save/reopen, Studio preview and real FFmpeg output-frame evidence, including speed/crossfade and caption/watermark stacking. Broader compositing, creative quality and commercial release remain unverified.",
   "evidence": [
    "docs/exec-plans/sprint-creation-render.md",
    "tests/test_creation_render.py",
    "scripts/render-creation.ps1",
    "docs/exec-plans/sprint-creation-workspace.md",
    "tests/test_creation_jobs.py",
    "tests/test_creation_workspace_browser.py",
    "docs/exec-plans/sprint-clip-speed.md",
    "tests/test_clip_speed_core.py",
    "tests/test_clip_speed_render.py",
    "tests/test_clip_speed_browser.py",
    "docs/exec-plans/sprint-clip-transitions.md",
    "tests/test_clip_transition_core.py",
    "tests/test_clip_transition_render.py",
    "tests/test_clip_transition_browser.py",
    "docs/archive/sprints/sprint-t23-render-safe-area-badge.md",
    "tests/test_creation_presentation.py",
    "src/gamingcreator/domain/creation_presentation.py",
    "docs/exec-plans/sprint-timed-overlays.md",
    "tests/test_creation_overlays.py",
    "tests/test_overlay_assets.py",
    "tests/test_overlay_http.py",
    "tests/test_overlay_render.py",
    "tests/test_overlay_revisions.py",
    "tests/test_overlay_composition.py",
    "tests/test_studio_overlays_browser.py"
   ],
   "done": "FFmpeg本地渲染MP4：裁剪拼接、变速、转场、音频混合、定时文字/图片叠层，均有真实输出帧证据",
   "todo": "更复杂合成未做；成片创意质量与商用发布未验证",
   "updated": "2026-11-07",
   "sprints": [
    "sprint-creation-render",
    "sprint-clip-speed",
    "sprint-clip-transitions",
    "sprint-timed-overlays"
   ]
  },
  {
   "id": "P029",
   "group": "D",
   "name": "字幕",
   "first": true,
   "delivery": "partial",
   "impl": "partial",
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": "Local ASR probe finds no word-level timestamps (worker/store/segment-only); mapper ready only for real provider words — timings are not invented. Word styling and creative quality remain unverified.",
   "evidence": [
    "docs/exec-plans/sprint-creation-subtitles.md",
    "tests/test_creation_subtitles.py",
    "tests/test_creation_subtitle_render.py",
    "tests/test_creation_workspace_http.py",
    "docs/exec-plans/sprint-creation-caption-editing.md",
    "tests/test_creation_caption_editing.py",
    "docs/exec-plans/sprint-clip-speed.md",
    "tests/test_clip_speed_core.py",
    "tests/test_clip_speed_render.py",
    "tests/test_clip_speed_browser.py",
    "docs/exec-plans/sprint-clip-transitions.md",
    "tests/test_clip_transition_core.py",
    "tests/test_clip_transition_render.py",
    "tests/test_clip_transition_browser.py",
    "docs/archive/sprints/sprint-t24-subtitle-word-timing.md",
    "tests/test_asr_word_timing.py",
    "src/gamingcreator/application/asr_word_timing.py",
    "docs/exec-plans/sprint-studio-caption-editor.md",
    "tests/test_studio_caption_editor_browser.py",
    "docs/exec-plans/sprint-studio-caption-preview.md",
    "tests/test_studio_caption_preview.py",
    "tests/test_studio_caption_preview_browser.py"
   ],
   "done": "按镜头生成/编辑字幕，草稿即时预览并烧入；烧入可选三种样式（标准/大字/半透明底框），预览同步近似显示",
   "todo": "本机ASR无逐字时间戳，逐字字幕未做；字体/颜色自定义与字幕质量未人评",
   "updated": "2026-11-10",
   "sprints": [
    "sprint-creation-subtitles",
    "sprint-creation-caption-editing",
    "sprint-studio-caption-editor",
    "sprint-studio-caption-preview"
   ]
  },
  {
   "id": "P030",
   "group": "D",
   "name": "BGM 选择与节奏匹配",
   "first": true,
   "delivery": "partial",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [
    "docs/exec-plans/sprint-creation-audio-mix.md",
    "tests/test_music_library.py",
    "tests/test_creation_audio_render.py",
    "tests/test_creation_audio_jobs.py",
    "tests/test_creation_audio_browser.py"
   ],
   "done": "本地曲库登记/手选、音量/闪避与真实混音；本机估计配乐节拍（BPM+拍点），Studio一键预览把剪辑点对齐到拍点（只缩短镜头）",
   "todo": "AI选曲与情绪匹配未做；节拍为本机估计未人工核对；曲目授权与响度质量未核",
   "updated": "2026-11-10",
   "sprints": [
    "sprint-creation-audio-mix"
   ]
  },
  {
   "id": "P031",
   "group": "D",
   "name": "封面／标题／简介／Tags",
   "first": true,
   "delivery": "partial",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [
    "docs/exec-plans/sprint-publication-assets.md",
    "tests/test_creation_publication.py",
    "tests/test_creation_publication_http.py",
    "tests/test_creation_publication_browser.py"
   ],
   "done": "从成片选帧做封面；标题/简介/标签有本地模板草稿（简介列出成片镜头已保存画面要点，标签含必须主题），可编辑保存多版本、下载；发布页可一键复制标题/简介/标签/全部",
   "todo": "无模型生成文案；封面设计与文案质量未评估",
   "updated": "2026-11-11",
   "sprints": [
    "sprint-publication-assets"
   ]
  },
  {
   "id": "P032",
   "group": "D",
   "name": "轻量编辑器（调入出点、换镜头、改字幕、换 BGM、重渲染）",
   "first": true,
   "delivery": "partial",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [
    "docs/exec-plans/sprint-creation-editing.md",
    "tests/test_creation_editing.py",
    "tests/test_creation_revision_jobs.py",
    "tests/test_creation_editing_browser.py",
    "docs/exec-plans/sprint-creation-caption-editing.md",
    "tests/test_creation_caption_editing.py",
    "docs/exec-plans/sprint-clip-speed.md",
    "tests/test_clip_speed_core.py",
    "tests/test_clip_speed_render.py",
    "tests/test_clip_speed_browser.py",
    "docs/exec-plans/sprint-clip-transitions.md",
    "tests/test_clip_transition_core.py",
    "tests/test_clip_transition_render.py",
    "tests/test_clip_transition_browser.py",
    "docs/exec-plans/sprint-clip-replacements.md",
    "tests/test_clip_replacement_core.py",
    "tests/test_clip_replacement_jobs.py",
    "tests/test_clip_replacement_http.py",
    "tests/test_clip_replacement_browser.py",
    "docs/exec-plans/sprint-studio-caption-editor.md",
    "tests/test_studio_caption_editor_browser.py"
   ],
   "done": "Studio可调出入点、换镜头、改字幕、换BGM/旁白、变速转场并另存版本重渲染；支持逐步撤销/重做（Ctrl+Z）",
   "todo": "编辑器整体易用性未经人工验收；部分编辑项仍不完整",
   "updated": "2026-11-11",
   "sprints": [
    "sprint-creation-editing",
    "sprint-clip-replacements",
    "sprint-studio-caption-editor",
    "sprint-studio-workbench"
   ]
  },
  {
   "id": "P033",
   "group": "D",
   "name": "专业剪辑软件导出（FCPXML／OTIO／Premiere XML）",
   "first": false,
   "delivery": "partial",
   "impl": "partial",
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": "Best-effort caption/stereo tracks exist in export fixtures; Final Cut/DaVinci/Premiere import is not claimed. Styling and NLE round-trip remain unverified.",
   "evidence": [
    "2026-11-01: FCPXML 1.9 and OTIO JSON export of saved revisions with source file URIs, frame-aligned rational times, speed time maps and crossfades as centred transitions with whole-frame trims so exported length equals the render; real 34-clip revision exported (299/30s); not import-verified in Final Cut/DaVinci/Premiere; no Premiere XML or audio/subtitle tracks",
    "docs/archive/sprints/sprint-t25-timeline-export-av-tracks.md",
    "tests/test_timeline_export_av_tracks.py",
    "2026-11-01 T25: best-effort FCPXML title lane + stereo audio-channel-source, OTIO A1/Captions tracks, xmeml audio track + caption markers; NLE import still unverified",
    "docs/exec-plans/sprint-premiere-narration-track.md",
    "tests/test_premiere_narration_export.py",
    "tests/test_studio_timeline_download_browser.py"
   ],
   "done": "导出FCPXML 1.9、OTIO、Premiere XML时间线，含尽力而为的字幕/音轨和独立旁白轨",
   "todo": "未在Final Cut/DaVinci/Premiere实际导入验证；样式往返未验证",
   "updated": "2026-11-08",
   "sprints": [
    "sprint-timeline-export",
    "sprint-premiere-narration-track"
   ]
  },
  {
   "id": "P034",
   "group": "E",
   "name": "平台规格配置（抖音／快手／B站／小红书，不硬编码）",
   "first": true,
   "delivery": "partial",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [
    "docs/exec-plans/sprint-platform-packages.md",
    "tests/test_platform_package.py",
    "tests/test_platform_package_browser.py",
    "2026-11-01: versioned platform-presets-v1 manifest + platform_preset_loader loads bilibili/douyin/kuaishou/xiaohongshu JSON locally; Source remains local_preset (非官方规则); page edits still create RuleVersion-edited overrides; limits stay null/not_configured — not claimed as official verification"
   ],
   "done": "四平台规格为本地可编辑预设（local-v2）；快手15分钟/4G、B站10小时按官方公开页填写并附原文出处",
   "todo": "抖音/小红书及各平台标题、简介、标签上限无可读官方页，仍未配置；不能宣称官方合规",
   "updated": "2026-11-10",
   "sprints": [
    "sprint-platform-packages"
   ]
  },
  {
   "id": "P035",
   "group": "E",
   "name": "主项目多版本（一稿多平台）",
   "first": false,
   "delivery": "partial",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [
    "docs/exec-plans/sprint-platform-packages.md",
    "tests/test_platform_package.py",
    "tests/test_platform_package_browser.py",
    "docs/exec-plans/sprint-studio-multi-platform-packages.md",
    "tests/test_studio_multi_platform.py"
   ],
   "done": "同一成片可在Studio串行生成多平台独立发布包，可恢复已提交任务并列出各平台结果",
   "todo": "按平台智能改时长/Hook/CTA的变体未做，无持久批量队列",
   "updated": "2026-11-08",
   "sprints": [
    "sprint-studio-multi-platform-packages",
    "sprint-platform-packages"
   ]
  },
  {
   "id": "P036",
   "group": "E",
   "name": "发布包导出",
   "first": true,
   "delivery": "partial",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [
    "docs/exec-plans/sprint-platform-packages.md",
    "tests/test_platform_package.py",
    "tests/test_platform_package_browser.py"
   ],
   "done": "可导出平台尺寸变体视频＋封面＋文案七文件ZIP，真实ZIP已验证，Studio可按序构建与恢复",
   "todo": "真实平台投稿可用性与商用权利未验，质量未单独评估",
   "updated": "2026-11-08",
   "sprints": [
    "sprint-platform-packages",
    "sprint-publication-assets"
   ]
  },
  {
   "id": "P037",
   "group": "E",
   "name": "投稿前检查（Preflight）",
   "first": true,
   "delivery": "partial",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [
    "docs/exec-plans/sprint-platform-packages.md",
    "tests/test_platform_package.py",
    "tests/test_platform_package_browser.py"
   ],
   "done": "发布包生成时做本地限值与资格检查，结果写入包内并在页面展示，blocked会阻止沙箱发布",
   "todo": "多数平台限值仍未配置（无官方可读来源），检查质量未经人评",
   "updated": "2026-11-10",
   "sprints": [
    "sprint-platform-packages"
   ]
  },
  {
   "id": "P038",
   "group": "E",
   "name": "自动发布",
   "first": false,
   "delivery": "partial",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [
    "2026-11-01: publishing adapter boundary with a local sandbox target only: package re-verification, local-check and blocked-eligibility gates, persisted submitted->processing->published simulation with status and history APIs; real platform targets refused pending official API access, account authorization and user approval; real guide package sandbox-published"
   ],
   "done": "本机沙箱发布：核验包与本地检查后模拟提交→处理→发布，可查状态与历史；已解冻",
   "todo": "真实平台未接入，需官方API、账号授权及你的单独同意",
   "updated": "2026-11-01",
   "sprints": [
    "sprint-sandbox-publish"
   ]
  },
  {
   "id": "P039",
   "group": "F",
   "name": "正式 Windows 桌面 EXE",
   "first": true,
   "delivery": "partial",
   "impl": "partial",
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": "License/gap visibility after build/install/smoke is present; clean-machine test, code signing, and resolving gaps.json redistribution questions remain.",
   "evidence": [
    "2026-11-01: thin Windows desktop host EXE built with the Windows-bundled C# compiler; single instance, random 127.0.0.1 port, kill-on-close Job Object stops the service tree, Edge app-mode window with a dedicated profile; smoke and real window-close tests leave no service processes; WebView2 embedding awaits SDK download approval; installer/clean-machine/signing not done",
    "2026-11-01: embedded WebView2 window using the user-approved pinned SDK 1.0.4314.35 (NuGet SHA512 verified, per-file SHA256 checked each build), dedicated profile, external links to the system browser, Edge app-mode fallback; real run: 6 WebView2 processes, page 200, no leftovers after close",
    "2026-11-01: build-app assembles a self-contained, movable portable app folder (bundled CPython, runtime packages without dev tools, package install instead of editable link, FFmpeg, EXE+WebView2; 660 MB under a 1.5 GB cap); packaged interpreter imports its own code; smoke passes and still passes after moving the folder; no installer, clean-machine test or signing yet",
    "2026-11-01: install-app installs/upgrades/uninstalls the built app per user without registry or shortcuts; upgrades swap only program parts (user data kept) with rollback on failure; uninstall keeps data; real 660 MB install+smoke ~10 s, upgrade and uninstall verified then removed; 5 installer tests including locked-file rollback; no clean-machine test or signing yet",
    "docs/archive/sprints/sprint-t27-license-gaps-visibility.md",
    "scripts/license_visibility.py",
    "tests/test_license_visibility.py",
    "2026-11-01 T27: build-app/install-app (+Smoke) print reminder to read licenses/THIRD-PARTY-NOTICES.md and licenses/gaps.json; no download to fill gaps"
   ],
   "done": "可构建便携版EXE（内嵌WebView2、自带Python/FFmpeg），可安装/升级/卸载；启动即进入Studio并沿用固定端口（片段篮/草稿重开不丢），不选WebView2禁用端口",
   "todo": "干净机器测试、代码签名、第三方许可缺口审阅仍待完成",
   "updated": "2026-11-10",
   "sprints": [
    "sprint-desktop-host"
   ]
  },
  {
   "id": "P040",
   "group": "F",
   "name": "桌面工作区（素材／预览／Agent 对话／时间线）",
   "first": false,
   "delivery": "partial",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [
    "docs/exec-plans/sprint-creation-workspace.md",
    "tests/test_creation_jobs.py",
    "tests/test_creation_workspace_browser.py"
   ],
   "done": "新工作台/studio可看素材、选方案、时间线剪辑、旁白音乐、字幕与导出；导出后一键去发布、禁用按钮显示原因、作品列表中文状态与失败原因、空项目三步引导；片段篮清空可恢复、渲染按本机历史显示预计耗时",
   "todo": "J1全流程第四次试看未通过；Agent对话区与人评验收未完成",
   "updated": "2026-11-11",
   "sprints": [
    "sprint-studio-workbench",
    "sprint-creation-workspace",
    "sprint-j1-creation-usability"
   ]
  },
  {
   "id": "P041",
   "group": "F",
   "name": "自然语言修改真实时间线（“前 5 秒太慢”）",
   "first": true,
   "delivery": "partial",
   "impl": "partial",
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": "Deterministic local commands and separately confirmed text-model proposals support bounded clip edits and existing overlay end/fade timing. Fake transports prove validation, recovery and real export flow; actual model semantic understanding and edit creative quality remain unverified.",
   "evidence": [
    "2026-11-01: rule-based Chinese timeline commands (speed/delete/move/swap/trim/transitions) previewed via stateless API, applied in the editor and persisted through normal revision validation with ancestor undo; whole-command refusal for unknown/impossible clauses; 20 parser/HTTP tests + browser preview/apply/save test; real 35-clip revision -> 34 clips saved as d7d7a4d5 with narration inherited; no model understanding",
    "docs/archive/sprints/sprint-t26-timeline-command-corpus.md",
    "tests/test_timeline_commands.py",
    "2026-11-01 T26: expanded accept/reject Chinese corpus (rule-v4-corpus); refuses cloud-model / merge / reverse / illegal speed talk; no unapproved cloud models",
    "docs/exec-plans/sprint-ai-overlay-timing.md",
    "tests/test_creation_overlay_reasoning.py",
    "tests/test_overlay_reasoning_e2e_browser.py",
    "tests/test_studio_overlay_reasoning_browser.py"
   ],
   "done": "规则版中文指令改镜头（快慢/删/换序/裁剪/转场）可预览应用保存；确认后的文字模型可调图层时间",
   "todo": "真实模型语义理解与修改创意质量未验证，开放式说法不支持",
   "updated": "2026-11-07",
   "sprints": [
    "sprint-timeline-commands",
    "sprint-ai-overlay-timing"
   ]
  },
  {
   "id": "P042",
   "group": "F",
   "name": "用户修改记录与数据反馈闭环",
   "first": false,
   "delivery": "partial",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [
    "2026-11-01: read-only local feedback statistics from saved creation jobs (plans, recommendation offered/adopted, revisions, edit kinds by actual difference including inherited settings, render->publication->package funnel); real demo-phase0 22 plans/18 chains in 0.6s; adoption so far from agent test runs, not human choices; not yet fed back into ranking",
    "2026-11-01: plan jobs capture per-structure finished-video counts from this project's saved records at registration; the planner moves frequently finished generic structures forward (mode template stays first/recommended), marks localRenders on cards and records ordering basis in the plan report; statistics failures fall back to template order",
    "2026-11-01 T9: when local editKinds show 裁剪 ≥3 and ≥50% of edit events, new plans cap each segment to 1.0s output, prepend advisory 「你常裁短，已建议更短片段」, and record thresholds/rule/observed counts under ordering.editHabits (frozen at registration in input/edit-habits.json); no silent duration change without that record; other edit kinds unchanged"
   ],
   "done": "本机统计推荐采用率、常见修改与成片→发布包漏斗；常用结构前移，频繁裁剪时自动缩短片段并记录依据",
   "todo": "采用数据多来自Agent测试而非真人；更深权重学习未做",
   "updated": "2026-11-01",
   "sprints": [
    "sprint-creation-feedback",
    "sprint-j1-feedback-iteration"
   ]
  },
  {
   "id": "P043",
   "group": "G",
   "name": "玩法展示",
   "first": true,
   "delivery": "partial",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [
    "2026-11-01: feature showcase mode (richest-description opening hook, ordered showcase, closing) real instance demo-phase0 -> 10-shot MP4 373 frames -> cover/text -> Bilibili package, all configured checks pass (.cache/content-modes-e2e.json); hook chosen by description detail, not visual understanding",
    "2026-11-01 T28: unified honesty copy on plan cards/help — 描述代理评分、非画面理解／未做人评／投放未验证; cross-linked docs/references/creation-guide.md; tests/test_mode_honesty.py + browser copy contracts; docs/archive/sprints/sprint-t28-content-mode-honesty.md"
   ],
   "done": "玩法展示模板：开场高光→顺序展示→收尾，真实录像→MP4→B站包已走通，即J1主路径",
   "todo": "J1第四次试看全流程未通过；高光靠描述而非画面理解",
   "updated": "2026-11-08",
   "sprints": [
    "sprint-content-modes",
    "sprint-j1-creation-usability"
   ]
  },
  {
   "id": "P044",
   "group": "G",
   "name": "活动投稿",
   "first": true,
   "delivery": "partial",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [
    "2026-11-01: campaign mode (opening, mandatory-topic clips in topic order, highlights, closing; missing topic stays a gap) real instance with topic 贝多芬 -> MP4 390 frames -> Bilibili package passing configured checks; activity rule parsing (P020) not done",
    "2026-11-01 T28: unified honesty copy on plan cards/help — 描述代理评分、非画面理解／未做人评／投放未验证; cross-linked docs/references/creation-guide.md; tests/test_mode_honesty.py + browser copy contracts; docs/archive/sprints/sprint-t28-content-mode-honesty.md"
   ],
   "done": "活动投稿模板按必须主题取片、缺主题报缺口；Studio可引用本地活动规则生成简报",
   "todo": "成片质量与真实投稿未经人评，平台活动规则仍需手动录入",
   "updated": "2026-11-08",
   "sprints": [
    "sprint-content-modes",
    "sprint-activity-rules"
   ]
  },
  {
   "id": "P045",
   "group": "G",
   "name": "攻略",
   "first": true,
   "delivery": "partial",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [
    "2026-11-01: guide mode (evenly spaced numbered steps, spoken step numbers follow current order) real instance -> MP4 372 frames -> Bilibili package passing configured checks; real guide correctness not human-reviewed",
    "2026-11-01 T28: unified honesty copy on plan cards/help — 描述代理评分、非画面理解／未做人评／投放未验证; cross-linked docs/references/creation-guide.md; tests/test_mode_honesty.py + browser copy contracts; docs/archive/sprints/sprint-t28-content-mode-honesty.md"
   ],
   "done": "攻略模板按录像均匀取第N步并读步号，真实录像→MP4→B站包已走通",
   "todo": "攻略逻辑与正确性未经人工评审",
   "updated": "2026-11-01",
   "sprints": [
    "sprint-content-modes"
   ]
  },
  {
   "id": "P046",
   "group": "G",
   "name": "游戏解说",
   "first": false,
   "delivery": "partial",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [
    "2026-11-01: commentary mode template (ordered ~3s segments, opening/commentary/ending roles, closing line) real demo-phase0 instance -> 315-frame MP4 -> Bilibili package passing configured checks (.cache/content-modes-e2e-r3.json)",
    "2026-11-01 T28: unified honesty copy on plan cards/help — 描述代理评分、非画面理解／未做人评／投放未验证; cross-linked docs/references/creation-guide.md; tests/test_mode_honesty.py + browser copy contracts; docs/archive/sprints/sprint-t28-content-mode-honesty.md"
   ],
   "done": "游戏解说模板约3秒/段顺序取材并留解说时间，真实出片＋B站包已走通；已解冻",
   "todo": "解说文案与成片质量未经人评",
   "updated": "2026-11-01",
   "sprints": [
    "sprint-content-modes"
   ]
  },
  {
   "id": "P047",
   "group": "G",
   "name": "实况精剪",
   "first": false,
   "delivery": "partial",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [
    "2026-11-01: live-cut mode template (ordered ~1.5s segments, best-scored clip near each slot) real instance -> 445-frame MP4 -> Bilibili package passing configured checks",
    "2026-11-01 T28: unified honesty copy on plan cards/help — 描述代理评分、非画面理解／未做人评／投放未验证; cross-linked docs/references/creation-guide.md; tests/test_mode_honesty.py + browser copy contracts; docs/archive/sprints/sprint-t28-content-mode-honesty.md"
   ],
   "done": "实况精剪模板约1.5秒/段按顺序紧凑取材，真实出片＋B站包已走通；已解冻",
   "todo": "剪辑节奏与成片质量未经人评",
   "updated": "2026-11-01",
   "sprints": [
    "sprint-content-modes"
   ]
  },
  {
   "id": "P048",
   "group": "G",
   "name": "高光",
   "first": false,
   "delivery": "partial",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [
    "2026-11-01: highlight mode template (top-scored clips in recording order, best last as climax) real instance -> 445-frame MP4 -> Bilibili package; scores are description proxies, not visual understanding",
    "2026-11-01 T28: unified honesty copy on plan cards/help — 描述代理评分、非画面理解／未做人评／投放未验证; cross-linked docs/references/creation-guide.md; tests/test_mode_honesty.py + browser copy contracts; docs/archive/sprints/sprint-t28-content-mode-honesty.md"
   ],
   "done": "高光模板取评分最高片段按顺序、最高分作收尾，真实出片＋B站包已走通；已解冻",
   "todo": "评分是描述代理而非画面理解，质量未经人评",
   "updated": "2026-11-01",
   "sprints": [
    "sprint-content-modes"
   ]
  },
  {
   "id": "P049",
   "group": "G",
   "name": "广告／买量",
   "first": false,
   "delivery": "partial",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [
    "2026-11-01: ad/UA mode template (hook, up to three selling points preferring mandatory topics, call to action) real instance -> 270-frame MP4 -> Bilibili package; ad performance unknown",
    "2026-11-01 T28: unified honesty copy on plan cards/help — 描述代理评分、非画面理解／未做人评／投放未验证; cross-linked docs/references/creation-guide.md; tests/test_mode_honesty.py + browser copy contracts; docs/archive/sprints/sprint-t28-content-mode-honesty.md"
   ],
   "done": "广告/买量模板：钩子＋最多3卖点＋行动号召，真实出片＋B站包已走通；已解冻",
   "todo": "投放效果未知，质量未经人评",
   "updated": "2026-11-01",
   "sprints": [
    "sprint-content-modes"
   ]
  },
  {
   "id": "P050",
   "group": "H",
   "name": "创作者版（Free／Creator／Pro）",
   "first": false,
   "delivery": "partial",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [
    "2026-11-01: local creator-plan entitlement model (founder default unlimited, Free/Creator/Pro) enforced at real entry points: monthly render quota metered from saved jobs, one platform package per publication on Free, activity-rule parsing, timeline export and sandbox publish gates; plan selection marked local evaluation; no payment, subscription, signed license or watermark",
    "2026-11-01: Free renders burn a top-right semi-transparent 'GamingCreator Free' mark via ASS; decided at registration and stored on the job, recorded in the render receipt and checked on verify; founder/creator/pro unmarked; real FFmpeg pixel test and job-level test; analysis-minute metering and payments still absent"
   ],
   "done": "本地Free/Creator/Pro套餐模型：月渲染配额、Free包数限制与水印、功能门槛已生效（本地评估）",
   "todo": "无支付、订阅、签名许可证；分析分钟计量未做",
   "updated": "2026-11-01",
   "sprints": [
    "sprint-creator-plans"
   ]
  },
  {
   "id": "P051",
   "group": "H",
   "name": "企业版",
   "first": false,
   "delivery": "partial",
   "impl": null,
   "quality": "not_separately_assessed",
   "release": "not_released",
   "remaining": null,
   "evidence": [
    "2026-11-01: local team model with owner/editor/reviewer/viewer roles, brand glossary checks on package title/description/tags, package review with separation of duties, mandatory rejection reasons and append-only history, review-gated sandbox publishing; real package submit->approve->publish test; no accounts/login, shared storage, enterprise assets, external API or seat billing; no page entry yet",
    "2026-11-01 T10: per-project teams (sha256 path under enterprise/teams) with read-only fallback to legacy global enterprise-team.json; append-only audit jsonl plus GET /api/enterprise/audit JSON/CSV marked actorSelfReported; creation page expandable review history, audit export links, and honest self-reported operator copy; review/publish use the package project's team"
   ],
   "done": "本机团队角色、品牌词检查、发布包审核与职责分离、审计导出，审核通过才可沙箱发布",
   "todo": "无账号登录、共享存储、企业素材库、外部API与席位计费",
   "updated": "2026-11-01",
   "sprints": [
    "sprint-enterprise-basics"
   ]
  }
 ],
 "phase0": [
  {
   "id": "F000",
   "name": "Technical reverse review",
   "description": "Review the source plan for feasibility, architecture, model capability, video processing, cost, and one-person maintenance; refine the smallest Phase 0 loop.",
   "passes": true,
   "criteria": "A dated review in docs/exec-plans identifies key risks, evidence, decisions, and any changes to the Phase 0 scope."
  },
  {
   "id": "F001",
   "name": "CLI input and project skeleton",
   "description": "Prepare isolated, pinned CPython 3.13/uv/venv tools and a four-layer Python CLI package with typed domain/provider contracts and local input validation.",
   "passes": true,
   "criteria": "Reproducible package build, pytest/Ruff/mypy and import-direction checks pass using project-local tools/caches, with no Windows Python registration or global links; missing/unreadable video returns the specified input error without output."
  },
  {
   "id": "F002",
   "name": "Local media preprocessing",
   "description": "Use FFmpeg locally to probe media and extract timestamped audio and visual evidence.",
   "passes": true,
   "criteria": "Representative and synthetic VFR/nonzero-PTS clips produce traceable source timecodes; no-audio, malformed input and cancellation are handled cleanly."
  },
  {
   "id": "F003",
   "name": "Replaceable model analysis",
   "description": "Implement local ASR and replaceable vision analysis, produce validated semantic events, and record per-attempt model, usage and cost metadata.",
   "passes": true,
   "criteria": "Provider replacement is verified; ASR distinguishes no_audio/no_speech/failure; schema, usage, budget and retry checks pass with per-attempt model/prompt/cost/time records and unknown costs preserved."
  },
  {
   "id": "F004",
   "name": "Persistent semantic timeline",
   "description": "Store media references, timestamped semantic events, and analysis metadata in SQLite.",
   "passes": true,
   "criteria": "A second process reloads the timeline; migrations/FKs and interrupted-stage/file-integrity recovery pass; unknown request costs survive recovery; full source video bytes are absent from SQLite."
  },
  {
   "id": "F005",
   "name": "Natural-language clip retrieval",
   "description": "Rank timeline segments against a text query and return useful clip ranges with evidence.",
   "passes": true,
   "criteria": "A query returns stable, deduplicated source intervals with evidence from a Completed run; empty results are valid; lexical and semantic retrieval are compared on fixed fixtures."
  },
  {
   "id": "F006",
   "name": "Retrieval benchmark and gate",
   "description": "Evaluate ranked results against human judgments and report quality, runtime, and model cost.",
   "passes": false,
   "criteria": "A frozen independent human-labeled benchmark reports every query, fixed-denominator U10, misses/timecode errors, runtime and cold/hot cost; each main mechanic query reaches U10 >= 0.70; sparse/negative groups are separate and unverified cost gates remain null."
  },
  {
   "id": "F007",
   "name": "Local inspection workspace",
   "description": "User-authorized local project/run inspection, source playback, evidence, filtered timeline and selected-interval manifests; does not replace the F006 human gate or implement video rendering.",
   "passes": true,
   "criteria": "Registered source/evidence HTTP boundaries and Range/HEAD/errors pass; real existing footage supports search, seek/end pause, evidence preview, isolated basket restoration and identity-preserving JSON/CSV export; browser behavior checks cover stale responses and text safety using project-isolated tools."
  },
  {
   "id": "F008",
   "name": "Workspace layout and chronological clip basket",
   "description": "Apply user UI acceptance feedback: professional workstation layout with visible preview/timeline/basket, independent list scrolling and chronological selections without changing retrieval ranks.",
   "passes": true,
   "criteria": "Real browser checks show preview, timeline and basket together at 1440x900 and 1366x768 without page scrolling, keep a deep timeline position through selection, preserve all existing playback/evidence behavior, sort basket/storage/JSON/CSV by source start/end/identity and avoid mobile horizontal overflow."
  },
  {
   "id": "F009",
   "name": "Temporal gameplay analysis correction",
   "description": "Address rejected gameplay retrieval with ordered multi-frame action analysis, conservative action evidence and bounded real-video comparisons; this technical change does not pass F006.",
   "passes": false,
   "criteria": "A separately fingerprinted temporal prompt preserves legacy runs, rejects unordered or single-frame action claims, supports a denser source-clock-preserving profile and resumable windows, and records bounded real-video comparisons including static controls and all attempt costs. Independent action retrieval quality remains F006."
  },
  {
   "id": "F010",
   "name": "Actor-bound visual detail retrieval and clean descriptions",
   "description": "Address user feedback with visible appearance, clothing, held items, environment and action effects bound to their actors; remove internal frame aliases from human-facing descriptions while preserving frozen source facts.",
   "passes": false,
   "criteria": "Versioned V5/V6 detailed analysis and higher-resolution evidence preserve legacy contracts and resumable runs; uncertainty stays outside positive indexing and facts require review. Actor/part-bound observed attributes with shared supporting evidence must satisfy all strict compound constraints; unknown or cross-actor facts cannot be full matches. Original facts/basket validation remain intact; bounded real-video comparisons record every cost/control and independent human judgments confirm useful detail queries. F006 remains separate."
  }
 ],
 "roadmap": [
  {
   "id": "R1",
   "name": "创作主链",
   "goal": "需求+素材→可选方案→真实可解码MP4",
   "status": "partial",
   "done": "结构化需求、三种离线模板方案、素材缺口与EDL已通；EDL真实渲染MP4、工作台持久任务与/studio创作页可用",
   "todo": "J1人评第四次仍未通过；任意自然语言理解与创作质量人评未做",
   "features": [
    "P019",
    "P021",
    "P022",
    "P024",
    "P027",
    "P028",
    "P043",
    "P044",
    "P045"
   ],
   "slices": [
    {
     "id": "R1-1",
     "name": "首切片：素材→方案→剪辑决策",
     "status": "done",
     "sprint": "sprint-creation-planner"
    },
    {
     "id": "R1-2",
     "name": "第二切片：EDL真实渲染MP4",
     "status": "done",
     "sprint": "sprint-creation-render"
    },
    {
     "id": "R1-3",
     "name": "工作台创作与持久任务历史",
     "status": "done",
     "sprint": "sprint-creation-workspace"
    },
    {
     "id": "R1-4",
     "name": "三种内容模式离线模板",
     "status": "done",
     "sprint": "sprint-content-modes"
    },
    {
     "id": "R1-5",
     "name": "J1可用：创作页重做",
     "status": "partial",
     "sprint": "sprint-j1-creation-usability"
    },
    {
     "id": "R1-6",
     "name": "创作工作台 /studio",
     "status": "partial",
     "sprint": "sprint-studio-workbench"
    },
    {
     "id": "R1-7",
     "name": "J1第四次反馈迭代",
     "status": "partial",
     "sprint": "sprint-j1-feedback-iteration"
    }
   ]
  },
  {
   "id": "R2",
   "name": "完整制作",
   "goal": "改镜头/字幕/配乐/比例→重渲染→发布包",
   "status": "partial",
   "done": "镜头裁剪换序替换、变速、交叉淡化、逐镜字幕编辑与预览、本地配乐混音、本机旁白、定时图层、封面文案、四平台七文件包与时间线导出均有真实产物",
   "todo": "创意质量人评、AI文案/节拍匹配、商用曲目与声音权利、NLE真机导入未验",
   "features": [
    "P008",
    "P025",
    "P026",
    "P029",
    "P030",
    "P031",
    "P032",
    "P033",
    "P034",
    "P035",
    "P036",
    "P037"
   ],
   "slices": [
    {
     "id": "R2-A",
     "name": "镜头编辑、版本与重渲染",
     "status": "done",
     "sprint": "sprint-creation-editing"
    },
    {
     "id": "R2-B",
     "name": "手写字幕、版本继承与烧录",
     "status": "done",
     "sprint": "sprint-creation-caption-editing"
    },
    {
     "id": "R2-C",
     "name": "本地音乐登记与真实混音",
     "status": "done",
     "sprint": "sprint-creation-audio-mix"
    },
    {
     "id": "R2-D",
     "name": "真实封面与可编辑文案",
     "status": "done",
     "sprint": "sprint-publication-assets"
    },
    {
     "id": "R2-E",
     "name": "四平台变体与七文件包",
     "status": "done",
     "sprint": "sprint-platform-packages"
    },
    {
     "id": "R2-F",
     "name": "逐镜头变速与字幕/原声同步",
     "status": "done",
     "sprint": "sprint-clip-speed"
    },
    {
     "id": "R2-G",
     "name": "交叉淡化转场",
     "status": "done",
     "sprint": "sprint-clip-transitions"
    },
    {
     "id": "R2-H",
     "name": "从已选录像替换镜头",
     "status": "done",
     "sprint": "sprint-clip-replacements"
    },
    {
     "id": "R2-I",
     "name": "本地单段旁白",
     "status": "done",
     "sprint": "sprint-local-narration"
    },
    {
     "id": "R2-字幕",
     "name": "源语音映射成片字幕",
     "status": "done",
     "sprint": "sprint-creation-subtitles"
    },
    {
     "id": "P025",
     "name": "解说模板草稿",
     "status": "done",
     "sprint": "sprint-narration-script"
    },
    {
     "id": "P028",
     "name": "定时文字与PNG图层",
     "status": "done",
     "sprint": "sprint-timed-overlays"
    },
    {
     "id": "P033",
     "name": "专业时间线导出",
     "status": "done",
     "sprint": "sprint-timeline-export"
    },
    {
     "id": "P033-b",
     "name": "Studio时间线入口+Premiere旁白轨",
     "status": "done",
     "sprint": "sprint-premiere-narration-track"
    },
    {
     "id": "P029-a",
     "name": "Studio逐镜字幕编辑",
     "status": "done",
     "sprint": "sprint-studio-caption-editor"
    },
    {
     "id": "P029-b",
     "name": "Studio草稿字幕即时预览",
     "status": "done",
     "sprint": "sprint-studio-caption-preview"
    },
    {
     "id": "P035",
     "name": "Studio同版本多平台包",
     "status": "done",
     "sprint": "sprint-studio-multi-platform-packages"
    }
   ]
  },
  {
   "id": "R3",
   "name": "智能与七模式",
   "goal": "自然语言改片、规则/知识引用、七种视频模式",
   "status": "active",
   "done": "规则版一句话改镜头、活动规则离线提取并填需求、知识版本/出处进入策划与旁白；七模式均有真实出片+包；P018版本对比已实现",
   "todo": "P018批次完整门禁未绿未合main；开放语义理解、八维评分画面维度、联网抓取未做",
   "features": [
    "P018",
    "P020",
    "P023",
    "P041",
    "P042",
    "P046",
    "P047",
    "P048",
    "P049"
   ],
   "slices": [
    {
     "id": "P020",
     "name": "活动规则解析（离线）",
     "status": "done",
     "sprint": "sprint-activity-rules"
    },
    {
     "id": "P018",
     "name": "游戏知识层（本机）",
     "status": "done",
     "sprint": "sprint-game-knowledge"
    },
    {
     "id": "P018-cmp",
     "name": "补丁说明版本对比（当前）",
     "status": "done",
     "sprint": "sprint-knowledge-version-compare"
    },
    {
     "id": "P041",
     "name": "一句话改镜头（规则版）",
     "status": "done",
     "sprint": "sprint-timeline-commands"
    },
    {
     "id": "P041-b",
     "name": "AI编辑独立图层时间",
     "status": "done",
     "sprint": "sprint-ai-overlay-timing"
    },
    {
     "id": "P042",
     "name": "用户修改反馈闭环",
     "status": "done",
     "sprint": "sprint-creation-feedback"
    },
    {
     "id": "P023/P024",
     "name": "素材评分与缺口",
     "status": "done",
     "sprint": "sprint-material-scoring"
    },
    {
     "id": "R3-收口",
     "name": "Studio知识与本机旁白修订",
     "status": "done",
     "sprint": "sprint-studio-narration-revision"
    },
    {
     "id": "Grok-1",
     "name": "Grok工单一：Studio旁白工具与知识面板（T01–T32）",
     "status": "done",
     "sprint": "grok-studio-coding-checklist-20261108"
    },
    {
     "id": "Grok-2",
     "name": "Grok工单二：核心接入、旁白可编辑（R01–R48）",
     "status": "done",
     "sprint": "grok-studio-coding-round2-20261108"
    },
    {
     "id": "P030-beats",
     "name": "配乐节拍估计与剪辑点对齐",
     "status": "done",
     "sprint": ""
    }
   ]
  },
  {
   "id": "R4",
   "name": "桌面产品",
   "goal": "安装Windows EXE在桌面完成全流程",
   "status": "partial",
   "done": "EXE薄宿主+build/install脚本、许可缺口提示；360p编辑代理；启动器拒绝旧运行时",
   "todo": "干净机器安装实测、签名、许可证缺口确认、J3人评未做",
   "features": [
    "P011",
    "P039",
    "P040"
   ],
   "slices": [
    {
     "id": "P039",
     "name": "桌面EXE薄宿主",
     "status": "done",
     "sprint": "sprint-desktop-host"
    },
    {
     "id": "P011",
     "name": "编辑代理文件",
     "status": "done",
     "sprint": "sprint-editing-proxy"
    },
    {
     "id": "R4-rt",
     "name": "启动器拒绝旧运行时",
     "status": "done",
     "sprint": "sprint-workspace-runtime-identity"
    }
   ]
  },
  {
   "id": "R5",
   "name": "发布与商业化",
   "goal": "真实平台发布、创作者套餐、企业协作",
   "status": "partial",
   "done": "本机沙箱发布与状态查询；Free/Creator/Pro本地授权与额度生效；企业本机角色/审核门禁",
   "todo": "真实平台发布、支付订阅、账号登录与企业API均未接入，需单独授权",
   "features": [
    "P038",
    "P050",
    "P051"
   ],
   "slices": [
    {
     "id": "P038",
     "name": "自动发布（本机沙箱）",
     "status": "done",
     "sprint": "sprint-sandbox-publish"
    },
    {
     "id": "P050",
     "name": "创作者套餐（本地授权）",
     "status": "done",
     "sprint": "sprint-creator-plans"
    },
    {
     "id": "P051",
     "name": "企业版基础（本机团队）",
     "status": "done",
     "sprint": "sprint-enterprise-basics"
    }
   ]
  },
  {
   "id": "Q",
   "name": "持续质量与上线",
   "goal": "证明找得准、剪得对、可商业交付",
   "status": "partial",
   "done": "Phase0基础10项已交付；验收工具8/8就绪；OCR/镜头切分本地可用；缓存事故止血与限额；TD026付费输出留痕已实现",
   "todo": "质量已验收0/51；J2检索人评0/8步；完整门禁3失败修复待复验；未跑Release",
   "features": [
    "P001",
    "P002",
    "P003",
    "P004",
    "P005",
    "P006",
    "P007",
    "P009",
    "P010",
    "P012",
    "P013",
    "P014",
    "P015",
    "P016",
    "P017"
   ],
   "slices": [
    {
     "id": "Q-ocr",
     "name": "本地画面文字识别",
     "status": "done",
     "sprint": "sprint-ocr-frames"
    },
    {
     "id": "Q-shot",
     "name": "镜头切分与黑屏检测",
     "status": "done",
     "sprint": "sprint-shot-boundaries"
    },
    {
     "id": "Q-cache",
     "name": "58GiB缓存事故回收",
     "status": "done",
     "sprint": "sprint-cache-reclamation"
    },
    {
     "id": "Q-sync",
     "name": "Phase0版本推送与文档同步",
     "status": "done",
     "sprint": "sprint-phase0-publication-sync"
    },
    {
     "id": "TD026",
     "name": "付费返回结果本机留痕",
     "status": "done",
     "sprint": "sprint-paid-output-evidence"
    },
    {
     "id": "Q-U10",
     "name": "检索各主查询前十可用≥70%（J2/F006）",
     "status": "todo",
     "sprint": ""
    },
    {
     "id": "Q-review",
     "name": "事实/结构/字幕/配音真人评审",
     "status": "todo",
     "sprint": ""
    },
    {
     "id": "Q-time",
     "name": "创作主动时间节省>60%",
     "status": "todo",
     "sprint": ""
    },
    {
     "id": "Q-commercial",
     "name": "安装/凭据/权利/费用/恢复证据",
     "status": "todo",
     "sprint": ""
    }
   ]
  }
 ],
 "stages": [
  {
   "id": "S1",
   "name": "Phase 0 技术验证",
   "output": "录像→语义时间线→自然语言找片段",
   "status": "partial",
   "note": "工程完成；检索质量验收0/8步，F006/F009/F010仍false",
   "entry": "—"
  },
  {
   "id": "S2",
   "name": "Creative Planner",
   "output": "一句话需求→3套视频方案",
   "status": "partial",
   "note": "结构化输入/模板/EDL及知识规则引用可用；自然语言理解与人评未过",
   "entry": "实现立即开展；质量/发布另验"
  },
  {
   "id": "S3",
   "name": "Edit Decision + FFmpeg",
   "output": "自动输出MP4",
   "status": "partial",
   "note": "真实渲染含变速/转场/字幕/图层/旁白已通；J1人评第四次未通过",
   "entry": "EDL合同可执行；审片独立"
  },
  {
   "id": "S4",
   "name": "正式 Windows EXE",
   "output": "桌面工作区（预览/Agent/时间线）",
   "status": "partial",
   "note": "EXE薄宿主与安装脚本已有；干净机器、签名、许可缺口与J3人评未做",
   "entry": "阶段 3"
  },
  {
   "id": "S5",
   "name": "活动规则/多平台/发布包",
   "output": "多平台版本+投稿前检查+发布包",
   "status": "partial",
   "note": "规则离线提取、四平台七文件包、本地Preflight已交；官方规则与商用资格待补",
   "entry": "按ADR-003并行实现；正式发布另验"
  },
  {
   "id": "S6",
   "name": "真实账号发布",
   "output": "创始人账号实测",
   "status": "todo",
   "note": "仅本机沙箱发布；真实平台发布需单独授权",
   "entry": "阶段 5"
  }
 ],
 "qualitySteps": [
  {
   "id": "Q1",
   "name": "素材录制分组/开发·测试划分",
   "toolReady": true,
   "executed": false,
   "owner": "用户",
   "note": "待你决定分组及是否补原始录像；不阻断开发"
  },
  {
   "id": "Q2",
   "name": "事前查询与原片参考（每主查询≥10事件）",
   "toolReady": true,
   "executed": false,
   "owner": "用户",
   "note": "依赖第1步；登记工具含计数与重叠提醒"
  },
  {
   "id": "Q3",
   "name": "冻结评测计划",
   "toolReady": true,
   "executed": false,
   "owner": "Agent",
   "note": "默认自动盘点，待前两步完成"
  },
  {
   "id": "Q4",
   "name": "分析素材（付费）",
   "toolReady": true,
   "executed": false,
   "owner": "用户批准费用提案→Agent",
   "note": "需你批准具体费用提案后执行"
  },
  {
   "id": "Q5",
   "name": "关联已完成分析版本",
   "toolReady": true,
   "executed": false,
   "owner": "用户选版本/Agent",
   "note": "依赖第4步"
  },
  {
   "id": "Q6",
   "name": "生成固定排名",
   "toolReady": true,
   "executed": false,
   "owner": "Agent",
   "note": "依赖第5步"
  },
  {
   "id": "Q7",
   "name": "前十名人工评分",
   "toolReady": true,
   "executed": false,
   "owner": "用户",
   "note": "排名生成后触发；J2人评仍未做"
  },
  {
   "id": "Q8",
   "name": "门槛报告（逐主查询≥7/10）",
   "toolReady": true,
   "executed": false,
   "owner": "Agent",
   "note": "F006仍false，验收0/8"
  }
 ],
 "journeyFixes": {
  "J1": [
   {
    "id": "J1-1",
    "name": "素材去重、搜索范围、短事件取景区间",
    "status": "done",
    "note": "11-05 合同1–3落地并浏览器验证；未经真人复测"
   },
   {
    "id": "J1-2",
    "name": "四个方案价值不足 / 动态策划",
    "status": "done",
    "note": "第2次授权调用成功：3套动态方案（20/20/19镜头）已采用进Studio；创作价值待你评价"
   },
   {
    "id": "J1-3",
    "name": "创作助手开放式对话",
    "status": "partial",
    "note": "规则版改镜头可用；开放式对话未做"
   },
   {
    "id": "J1-4",
    "name": "切镜卡顿 / BGM 重复",
    "status": "partial",
    "note": "缓冲暂停音轨已修；双槽预加载与转场一致性在工作分支（TD025）"
   },
   {
    "id": "J1-5",
    "name": "云端音色配置",
    "status": "done",
    "note": "默认免费本机声音，云端需显式选择并过费用门"
   },
   {
    "id": "J1-6",
    "name": "保存版本按钮灰色",
    "status": "done",
    "note": "禁用原因可见，修改可保存并重开"
   },
   {
    "id": "J1-7",
    "name": "平台包下载成 true.txt",
    "status": "done",
    "note": "根因确认：htm 裸 download 属性变成 download=\"true\"；平台包(11-05)与成片MP4(11-09)均改为真实文件名，静态守卫防复发"
   },
   {
    "id": "J1-8",
    "name": "邀请你复测 J1",
    "status": "todo",
    "note": "开发验证通过后再邀请；当前不要求操作"
   }
  ]
 },
 "releaseGates": [
  {
   "id": "RG1",
   "name": "第三方许可证缺口（6项）",
   "status": "todo",
   "source": "human-inputs T2 / licenses/gaps.json"
  },
  {
   "id": "RG2",
   "name": "TD003 固定 FFmpeg 来源与 GPL 义务",
   "status": "todo",
   "source": "tech-debt TD003"
  },
  {
   "id": "RG3",
   "name": "verify.ps1 -Release 门禁",
   "status": "todo",
   "source": "STATUS 第4条：本批未跑"
  },
  {
   "id": "RG4",
   "name": "干净机器安装/启动/卸载实测",
   "status": "todo",
   "source": "P039 / R4"
  },
  {
   "id": "RG5",
   "name": "代码签名",
   "status": "todo",
   "source": "P039"
  },
  {
   "id": "RG6",
   "name": "J3 你亲自试安装",
   "status": "todo",
   "source": "journeys.json J3"
  },
  {
   "id": "RG7",
   "name": "商用上线材料：发布账号/平台、授权音乐与品牌、支付与套餐",
   "status": "todo",
   "source": "user-actions.md；到 R5 执行前申请"
  }
 ],
 "gate": {
  "date": "2026-11-10",
  "scope": "完整门禁 verify.ps1（本批：测试修复、Studio衔接四项、离开确认与渲染进度、桌面固定端口、作品信息）",
  "result": "pass",
  "counts": "5150 过 · 6 跳 · 0 失败（33分）",
  "branch": "main",
  "merged": true,
  "note": "提交 03c3489 上运行；格式/Ruff/mypy/CLI 均通过。未跑 -Release"
 },
 "fees": [
  "2026-11-08：用户要求尽量避免PR/AE等大型软件。开发、日常验证和成片导出走项目FFmpeg/浏览器路径，专业格式为可选交接，实际导入保持未验。此前Premiere退出由用户手动关闭，不是软件故障；不转成人工待办。",
  "2026-11-09：用户先后授权2次动态策划调用，均已耗用：①估算¥0.0094516（7abf86df…，failed:validate_proposal，原输出留存）②估算¥0.0174276（成功并采用）。不得重发；新调用仍需新授权。",
  "2026-11-05：用户要求语音暂用免费本机声音；不自动切换云端。文本AI新调用仍需独立确认。",
  "每月预授权 ¥50，只用于你指定的素材；超出每次单独询问；硬发送门禁保留；未知费用不写成 0。",
  "P038、P046–P051 已于 2026-11-03 由你确认解冻（J1 第三次试看“初版过得去”）。真实平台发布、支付和付费调用仍各自需要你明确授权。"
 ],
 "now": [
  "最新完整门禁通过：5150过6跳0失败（03c3489，33分，经quiet.ps1）；未Release，不提升人评或整项状态。逐批记录见HANDOFF与提交历史。",
  "J1第四次反馈7组工程修复完毕（含下载true.txt根因、预览卡顿TD025）；近两日又补：一句话需求、缺口一键找素材、配乐节拍对齐、字幕样式、导出后去发布、禁用原因可见、离开前确认、渲染进度保持、作品列表信息、首次引导、桌面EXE进Studio且固定端口。等你复测J1。",
  "动态策划：两次授权调用均已耗用（¥0.0094516失败已修因；¥0.0174276成功），3套方案已采用为方案任务4c857005（artifacts/demo-phase0），质量待你评价；新调用需新授权。",
  "平台限值仅填官方可读来源（快手15分钟/4G、B站10小时，docs/references/platform-limits-sources.md）；其余待你登录后核对（可选）。",
  "进度看板docs/progress/index.html；分发前许可证缺口及TD003仍待处理。"
 ],
 "sprints": [
  {
   "file": "grok-studio-coding-checklist-20261108",
   "title": "给 Grok 的开发工单：Studio 旁白工具与知识面板",
   "ids": [],
   "date": "",
   "bytes": 18126
  },
  {
   "file": "grok-studio-coding-round2-20261108",
   "title": "给 Grok 的第二轮开发工单：核心接入、旁白可编辑与真实制作闭环",
   "ids": [],
   "date": "",
   "bytes": 25323
  },
  {
   "file": "sprint-activity-rules",
   "title": "P020：活动规则解析（离线）",
   "ids": [
    "P020"
   ],
   "date": "2026-11-01",
   "bytes": 6874
  },
  {
   "file": "sprint-ai-overlay-timing",
   "title": "AI 编辑独立图层时间（工作树实现中）",
   "ids": [
    "J1",
    "R3"
   ],
   "date": "2026-11-07",
   "bytes": 3296
  },
  {
   "file": "sprint-cache-reclamation",
   "title": "严重缓存事故：58.29 GiB测试中间文件（2026-10-31）",
   "ids": [],
   "date": "2026-10-31",
   "bytes": 7637
  },
  {
   "file": "sprint-clip-replacements",
   "title": "R2-H：从已选录像中替换镜头",
   "ids": [
    "R2-H"
   ],
   "date": "2026-10-31",
   "bytes": 9830
  },
  {
   "file": "sprint-clip-speed",
   "title": "R2-F：逐镜头变速与字幕/原声同步",
   "ids": [
    "P028",
    "R2-F"
   ],
   "date": "2026-10-31",
   "bytes": 4213
  },
  {
   "file": "sprint-clip-transitions",
   "title": "R2-G：交叉淡化转场与变速共存",
   "ids": [
    "R2-G"
   ],
   "date": "2026-10-31",
   "bytes": 9362
  },
  {
   "file": "sprint-content-modes",
   "title": "P022 + P043/P044/P045：首产品三种内容模式（离线模板）",
   "ids": [
    "P022",
    "P043",
    "P044",
    "P045"
   ],
   "date": "2026-11-01",
   "bytes": 3927
  },
  {
   "file": "sprint-creation-audio-mix",
   "title": "R2-C：本地音乐登记、版本化配乐与真实混音",
   "ids": [
    "R2-C"
   ],
   "date": "2026-10-30",
   "bytes": 5840
  },
  {
   "file": "sprint-creation-caption-editing",
   "title": "R2-B：手写镜头字幕、版本继承与真实烧录",
   "ids": [
    "R2-B"
   ],
   "date": "2026-10-30",
   "bytes": 3360
  },
  {
   "file": "sprint-creation-editing",
   "title": "R2-A：镜头编辑、版本与真实重渲染",
   "ids": [
    "R2-A"
   ],
   "date": "2026-10-30",
   "bytes": 4722
  },
  {
   "file": "sprint-creation-feedback",
   "title": "P042：用户修改反馈闭环（本机统计）",
   "ids": [
    "P042"
   ],
   "date": "2026-11-01",
   "bytes": 2902
  },
  {
   "file": "sprint-creation-planner",
   "title": "R1 首切片：真实保存素材→创作方案→剪辑决策",
   "ids": [
    "R1"
   ],
   "date": "2026-10-30",
   "bytes": 3248
  },
  {
   "file": "sprint-creation-render",
   "title": "R1第二切片：EDL真实渲染MP4",
   "ids": [],
   "date": "2026-10-30",
   "bytes": 2775
  },
  {
   "file": "sprint-creation-subtitles",
   "title": "R2字幕：源语音映射到成片字幕",
   "ids": [],
   "date": "2026-10-30",
   "bytes": 5056
  },
  {
   "file": "sprint-creation-workspace",
   "title": "R1工作台创作与持久任务历史",
   "ids": [],
   "date": "2026-10-30",
   "bytes": 7497
  },
  {
   "file": "sprint-creator-plans",
   "title": "P050：创作者套餐（本地授权模型）",
   "ids": [
    "P050"
   ],
   "date": "2026-11-01",
   "bytes": 2631
  },
  {
   "file": "sprint-desktop-host",
   "title": "P039（R4第一步）：桌面EXE薄宿主",
   "ids": [
    "P039"
   ],
   "date": "2026-11-01",
   "bytes": 8380
  },
  {
   "file": "sprint-editing-proxy",
   "title": "P011：编辑代理文件",
   "ids": [
    "P011"
   ],
   "date": "2026-11-01",
   "bytes": 2652
  },
  {
   "file": "sprint-enterprise-basics",
   "title": "P051：企业版基础（本机团队模型）",
   "ids": [
    "P051"
   ],
   "date": "2026-11-01",
   "bytes": 1930
  },
  {
   "file": "sprint-game-knowledge",
   "title": "P018：游戏知识层（本机）",
   "ids": [
    "P018"
   ],
   "date": "2026-11-08",
   "bytes": 6753
  },
  {
   "file": "sprint-j1-creation-usability",
   "title": "Sprint：J1 可用（创作页重做）",
   "ids": [
    "J1",
    "P038",
    "P046",
    "P051"
   ],
   "date": "2026-11-02",
   "bytes": 6748
  },
  {
   "file": "sprint-j1-feedback-iteration",
   "title": "J1 反馈迭代合同（2026-11-04）",
   "ids": [
    "J1"
   ],
   "date": "2026-11-07",
   "bytes": 14457
  },
  {
   "file": "sprint-knowledge-version-compare",
   "title": "P018 本机补丁说明版本对比",
   "ids": [
    "P018"
   ],
   "date": "2026-11-09",
   "bytes": 4211
  },
  {
   "file": "sprint-local-narration",
   "title": "R2-I：本地单段旁白",
   "ids": [
    "R2",
    "R2-I"
   ],
   "date": "2026-10-31",
   "bytes": 5312
  },
  {
   "file": "sprint-material-scoring",
   "title": "P023/P024：素材评分与缺口（离线）",
   "ids": [
    "P023",
    "P024"
   ],
   "date": "2026-11-01",
   "bytes": 2065
  },
  {
   "file": "sprint-narration-script",
   "title": "P025：解说模板草稿（单Agent）",
   "ids": [
    "P025"
   ],
   "date": "2026-10-31",
   "bytes": 1998
  },
  {
   "file": "sprint-ocr-frames",
   "title": "本地画面文字识别（ocr-frames-v1，2026-10-26第四会话）",
   "ids": [],
   "date": "2026-11-01",
   "bytes": 5432
  },
  {
   "file": "sprint-paid-output-evidence",
   "title": "TD026 付费返回结果的本机留痕",
   "ids": [
    "TD026"
   ],
   "date": "2026-11-09",
   "bytes": 2850
  },
  {
   "file": "sprint-phase0-publication-sync",
   "title": "Phase 0已验证版本推送与文档同步（2026-10-29）",
   "ids": [],
   "date": "2026-11-01",
   "bytes": 5166
  },
  {
   "file": "sprint-platform-packages",
   "title": "R2-E：配置驱动四平台变体与七文件预览包",
   "ids": [
    "P034",
    "R2-E"
   ],
   "date": "2026-11-01",
   "bytes": 5530
  },
  {
   "file": "sprint-premiere-narration-track",
   "title": "P033：Studio专业时间线入口与Premiere独立旁白轨",
   "ids": [
    "P033"
   ],
   "date": "2026-11-08",
   "bytes": 7831
  },
  {
   "file": "sprint-publication-assets",
   "title": "R2-D：真实封面与可编辑文案",
   "ids": [
    "R2-D"
   ],
   "date": "2026-10-31",
   "bytes": 3898
  },
  {
   "file": "sprint-sandbox-publish",
   "title": "P038：自动发布（本机沙箱）",
   "ids": [
    "P038"
   ],
   "date": "2026-11-01",
   "bytes": 1639
  },
  {
   "file": "sprint-shot-boundaries",
   "title": "本地镜头切分与黑屏检测（shot-boundaries-v1，2026-10-26第四会话）",
   "ids": [],
   "date": "2026-11-01",
   "bytes": 9709
  },
  {
   "file": "sprint-studio-caption-editor",
   "title": "Studio 逐镜字幕编辑",
   "ids": [
    "P029"
   ],
   "date": "2026-11-07",
   "bytes": 3650
  },
  {
   "file": "sprint-studio-caption-preview",
   "title": "Studio 草稿字幕即时预览",
   "ids": [
    "P029"
   ],
   "date": "2026-11-07",
   "bytes": 4190
  },
  {
   "file": "sprint-studio-multi-platform-packages",
   "title": "Studio 同一发布版本的多平台包",
   "ids": [
    "R2"
   ],
   "date": "2026-11-07",
   "bytes": 5712
  },
  {
   "file": "sprint-studio-narration-revision",
   "title": "Studio 知识与本机旁白修订收口",
   "ids": [
    "P018"
   ],
   "date": "2026-11-08",
   "bytes": 7513
  },
  {
   "file": "sprint-studio-workbench",
   "title": "Sprint：创作工作台（/studio）",
   "ids": [],
   "date": "2026-11-03",
   "bytes": 14861
  },
  {
   "file": "sprint-timed-overlays",
   "title": "P028 定时文字与 PNG 图层",
   "ids": [
    "P028"
   ],
   "date": "2026-11-07",
   "bytes": 4345
  },
  {
   "file": "sprint-timeline-commands",
   "title": "P041：一句话改镜头（规则版）",
   "ids": [
    "P041"
   ],
   "date": "2026-11-01",
   "bytes": 2381
  },
  {
   "file": "sprint-timeline-export",
   "title": "P033：专业时间线导出",
   "ids": [
    "P033"
   ],
   "date": "2026-11-01",
   "bytes": 2170
  },
  {
   "file": "sprint-workspace-runtime-identity",
   "title": "启动器拒绝旧运行时",
   "ids": [],
   "date": "2026-11-07",
   "bytes": 3386
  }
 ],
 "techDebt": [
  {
   "id": "TD001",
   "found": "2026-10-03/F002",
   "severity": "medium",
   "impact": "已识别showinfo／双ashowinfo记录已改流式消费，不再按完整日志16MiB拒绝长素材；未知诊断行与单行继续受限",
   "fix": "一小时合成带音轨、63.2MB时间记录／3600图／168752音频分段通过真实FFmpeg、保存及第二进程回读；取消／超时／错误回收和完整1912／1权限skip通过。真实游戏小时性能与全进程峰值由TD005继续跟踪，见sprint-long-footage-media",
   "status": "resolved; synthetic-hour capacity verified",
   "state": "resolved"
  },
  {
   "id": "TD002",
   "found": "2026-10-03/F002",
   "severity": "medium",
   "impact": "缺精确 stream start/duration/timebase 的容器被明确拒绝；2026-10-25 Matroska／WebM缺`duration_ts`已改为逐包`max(pts+duration)`补探测（MP4不变），真实6分钟钟馗MP4无损转MKV经CLI准备成功（406.762秒对MP4 406.7627秒）",
   "fix": "见media-processing.md；仍缺start_pts或timebase的容器继续拒绝；工作台内置Chromium已实测播放零起点MKV，非零PTS MKV的验收页自动映射未验证（TD006）；2026-10-25起目录扫描（`inventory-sources`及`validate-media／storage／asr -AllLocal`）共用`domain.media.LOCAL_VIDEO_SUFFIXES`（.mp4／.mkv／.webm），真实目录含MKV／WebM实测全部发现并精确探测",
   "status": "partial: Matroska/WebM supported and previewable in Chromium; acceptance-page mapping exact for zero-start MKV/WebM and audio-late WebM, other Matroska clocks fall back to manual (tested); other clockless containers open",
   "state": "partial"
  },
  {
   "id": "TD003",
   "found": "2026-10-03/F000",
   "severity": "release prerequisite",
   "impact": "当前 FFmpeg 是复制副本，固定 hash 不等于分发来源/许可证完整。2026-10-25本机识别：`ffmpeg version N-123317-gc1be2107c9-20260310`，gcc 15.2.0 crosstool-NG交叉编译、`--prefix=/ffbuild/prefix --enable-shared`，形态与BtbN FFmpeg-Builds的win64 GPL shared自动构建一致；含`--enable-gpl --enable-version3`及libx264／libx265等，分发须按GPLv3",
   "fix": "2026-10-25联网只读核对（GitHub公开tags页，未下载任何文件）：BtbN对较早日期只保留每月末构建（如`autobuild-2026-02-28-12-59`、`autobuild-2026-03-31-13-11`），本机2026-03-10当日构建已不再发布，**无法从原来源重新取得同一份**。因此发布前须改为固定一个仍可取得的构建（月末autobuild或发布系列），经用户许可下载后在toolchain.json写入地址与SHA256，并以新构建重跑媒体／存储／源时钟检查；现有副本继续仅供本机开发。原计划：发布前在toolchain.json固定该构建的可取得下载地址与SHA256（未联网核对，不推定具体发布资产）、审查 GPL 与第三方 notices；保持项目内安装",
   "status": "open",
   "state": "open"
  },
  {
   "id": "TD004",
   "found": "2026-10-04/F005",
   "severity": "high before F006",
   "impact": "v4有限否定规则已排除Atom jump的明确否定候选；Boss/射击/汽车维修hybrid为空，但pure semantic仍误召回，阈值未用人评校准，不能证明U10",
   "fix": "冻结独立人评/主稀疏负例查询，测否定/混合语义覆盖、pure semantic负例和片段边界",
   "status": "open",
   "state": "open"
  },
  {
   "id": "TD005",
   "found": "2026-10-04/F005",
   "severity": "medium",
   "impact": "1024整次请求限制已解除，固定batch=1；真实小时游戏全链路、总进程峰值及source hash I/O待测。一小时合成准备续跑的文件核对／映射重建仍25秒；素材任务清单metadata读取已独立，一小时完整详情首次5秒等待超时，实际打开耗时尚未验证，不循环优化",
   "fix": "已有2051文本／1280事件及真实E5 1281文本18.6s／2.6s证据；一小时合成实际本地准备／保存33秒、续准备25秒未重新抽帧、独立进程读回，见sprint-media-preparation与sprint-long-footage-media。2026-10-25真实长素材实测见下方TD005段；另择阶段优化重复核对。2026-10-25跨改动审查（code-quality-guard PASS）记一P2已知限制：第A步后带查询打开只在`inspect_run`哈希一次，`record_search`保存检索记录前不再重哈希，若检索（本地向量可能数秒）期间证据或原片被替换，该检索记录仍标`timeline_verified=True`；下一次打开会完整重核对、基准路径仍完整重哈希，不会带出错误身份。同日已修：`cli/main.py:execute_search`在时间线核对后（复用或新载两分支）记录原片与全部证据的(inode, size, mtime_ns)，保存前再取一次，有任何变化或文件消失即改为完整重哈希（被替换则`storage.integrity`拒绝保存）；只会多哈希、不会少哈希。新增`test_a_file_replaced_during_the_search_is_hashed_again_before_saving`（旧代码保存成功即失败、新代码拒绝），检索／工作台相关20个测试文件全部通过；单Agent改动（只收紧），未另派独立审查",
   "status": "partial: real 15-min resources measured; real hour-long footage unavailable locally",
   "state": "partial"
  },
  {
   "id": "TD006",
   "found": "2026-10-04/F007",
   "severity": "medium",
   "impact": "2026-10-24两验收页已交付实证Chromium／MP4非零PTS及异步A/V自动映射，条码画面oracle、动态有效态和旧包复用通过",
   "fix": "已测切片交付；无画面／未知仍手动，其他浏览器与更广编码兼容未验，见report-2026-10-24-source-clock-mapping.md；2026-10-25容器扩展：零起点MKV／WebM及音频晚起WebM自动映射逐帧通过，非零起点MKV／WebM与音频晚起MKV确定性退回手动（新增3个回退测试，同文件39项全过）",
   "status": "open（已测自动映射切片交付，广泛兼容待验）",
   "state": "open"
  },
  {
   "id": "TD007",
   "found": "2026-10-04/F009",
   "severity": "high before F006",
   "impact": "v4有效多帧JSON仍可能跨镜头关联、下落/jump歧义、标签/不确定性矛盾；静帧幻觉被拒绝使窗口失败，4秒跨度不能覆盖长动作/Boss遭遇",
   "fix": "冻结真实动作/切镜/静帧样本，比较更合适视觉Provider与事件表示、候选精分析/长窗口；保留失败与全部费用，独立人工验收；2026-10-26本地`detect-shots`（shot-boundaries-v1）可量化跨镜头：长钟馗272窗中41窗（约15%）的输入帧来自不同镜头，469事件中7个跨切换；只报告不改窗口，阈值未经人评，见sprint-shot-boundaries.md；2026-10-26离线归因（只读、仅汇总、未据此生成查询或标签）：41个跨镜头窗中39个在过场段（0–130秒、715秒后），玩法段仅2个；过场段内跨镜头与单镜头窗拒绝率2.6%对3.0%、每事件玩法标签0.70对0.71，跨镜头窗只是切成更多更短事件（每窗2.05对1.21）；uncertainty字段97–100%都填、不能区分。结论：本素材跨镜头不是玩法理解差的主因，按镜头切窗口的付费提案暂无依据，TD007改进应转向长动作／跳落歧义等",
   "status": "open",
   "state": "open"
  },
  {
   "id": "TD008",
   "found": "2026-10-04/F007",
   "severity": "low",
   "impact": "源/证据hash缓存依赖文件大小/mtime等身份变化，不能发现元数据完全不变的同大小外部改写。2026-10-25本机实测（项目CPython 3.13.16／Windows）：`st_ctime_ns`等于创建时间（`st_birthtime_ns`），写入后不变；因此`ui/media.py`的签名`(dev, ino, size, mtime, ctime)`识别不了“同大小原地改写并恢复修改时间”。工作台详情／检索的完整性检查不依赖此签名（每次逐字节核对，TD005第A步后仍如此），受影响的只是视频预览的已核对缓存",
   "fix": "2026-10-25已修普通情形：新增`infrastructure/file_identity.py:change_time_ns`，Windows上经已打开句柄读NTFS ChangeTime（文件系统对任何数据／元数据改动都会推进，包括恢复修改时间那一步本身），签名前后各取一次；非Windows沿用`st_ctime_ns`（本就是变更时间）。新增回归测试`test_verified_media_detects_rewrite_with_restored_times`（同大小原地改写＋精确恢复访问／修改时间，旧代码不报错、新代码拒绝）；每次调用约2.6微秒。剩余：刻意经原生接口连ChangeTime一起伪造仍防不住，FAT类卷ChangeTime可能恒为0时退化为原签名；需对抗此类时仍应强制重验",
   "status": "resolved for ordinary rewrites (restored mtime); deliberate ChangeTime forgery out of scope",
   "state": "resolved"
  },
  {
   "id": "TD009",
   "found": "2026-10-05/F010",
   "severity": "high before detail acceptance",
   "impact": "V5/V6紧凑事实可描述细节，但自由文本RRF不保证条件全部满足/同一主体/同一部件；恶魔领主复合例V6仍hybrid8局部候选，uncertainty不能抵消facts误分类，E5截断512token；2026-10-24独立静态声明导入／检索已交付，自动生成与真实外观质量未验证",
   "fix": "按actor-detail-matching-spec实现候选sidecar精分析与同actor/part AND、共同支持帧和uncertain保护；合同先冻结，再Provider/预算与Store/UI；独立复合人评，静态索引另立事件类型，不删除动作保护",
   "status": "open",
   "state": "open"
  },
  {
   "id": "TD010",
   "found": "2026-10-06/F005",
   "severity": "medium; resolved by later retrieval work",
   "impact": "正文明确否认某动作时裸mechanicTag曾可盖过否认保护（人工夹具17/18复现）",
   "fix": "2026-10-24复跑原复现`artifacts/action-tag-support/tag-denial-repro.py`（复制到.cache/td010作为pytest运行）：lexical／hybrid／semantic×6例18/18通过；由2026-10-22检索否认／标签噪声过滤改动覆盖，另有test_retrieval_local_completed_td010真实demo回归",
   "status": "resolved (verified 2026-10-24)",
   "state": "resolved"
  },
  {
   "id": "TD011",
   "found": "2026-10-07/F002",
   "severity": "low; local shell compatibility",
   "impact": "从当前Codex PowerShell 7环境拉起Windows PowerShell 5时，媒体校验包装脚本遇Get-FileHash不可用；移除继承模块路径也未解决，不继续反复定位",
   "fix": "当前使用已有PowerShell 7执行同一脚本和真实入口验证，不改全局环境／安装组件；后续需验证独立Windows PowerShell 5环境，不能称其通过；2026-10-25本机独立Windows PowerShell 5.1.26100（无PowerShell 7）从bash直接调用`test-media.ps1 -SourcePath artifacts/td002-probe/zhongkui-6min.mkv`退出0（407图、音频0间断），`Get-FileHash`来自Microsoft.PowerShell.Utility正常；完整`verify.ps1`同环境通过。原失败只在PowerShell 7父进程传入模块路径时出现",
   "status": "resolved (verified 2026-10-25 in standalone Windows PowerShell 5.1)",
   "state": "resolved"
  },
  {
   "id": "TD012",
   "found": "2026-10-07/F006",
   "severity": "low; intermittent verification environment",
   "impact": "2026-10-29跨进程状态占用最后两入口已修：验收status.json与批次state.json复用约1秒有限等待，短暂占用后正常保存，持续占用有界报错、原状态与准备输出保持；旧同进程锁／路径与10053修复保留。",
   "fix": "见[sprint](../archive/sprints/sprint-workflow-status-retry.md)：真实独立进程占用、身份/原字节保持及路径变链测试，新增21项；55项工作树定向与主树FFmpeg相关回归通过；Sol/high分两段审查PASS。",
   "status": "resolved 2026-10-29: bounded cross-process status/state file waits; original locks, identities, atomic writes and failure propagation preserved",
   "state": "resolved"
  },
  {
   "id": "TD013",
   "found": "2026-10-07/F002",
   "severity": "low; before first task only",
   "impact": "批次plan已冻结但SQLite尚未创建就中断时，resume的原项目存在性检查拒绝；尚无已创建任务，不影响已有任务恢复",
   "fix": "保留批次冻结资料，恢复环境后重新提交清单；后续明确仅对未创建任务的批次放开初始化，不能重建已丢失DB中的分析或未知费用。由本轮代码路径检查发现，未宣称真实硬杀在此窗口验证；2026-10-25已按此规则实现：`cli/main.py:require_resumable_project`——数据库缺失时，仅当项目顶层只有`media-batches`（及`.analysis-writer.lock`）、其下只有本批次、本批次目录只有四个冻结文件（及锁）时放行，取批次锁后再复核一次；工作台续跑走同一规则。新增5个测试（冻结后中断可续跑、store打开中断只留锁可续跑、runs／state／其他批次／WAL任一痕迹拒绝、持锁前出现痕迹被复核拒绝、工作台续跑及拒绝提示），code-quality-guard（opus）PASS，三项P2（测试覆盖、文档与工作台一致、错误码）已处理",
   "status": "resolved 2026-10-25: unstarted frozen batch resumable (CLI and workspace); any other trace still refuses",
   "state": "resolved"
  },
  {
   "id": "TD014",
   "found": "2026-10-07/F006",
   "severity": "medium; workflow status display",
   "impact": "读旧running后worker落终态释放锁导致误报interrupted的竞态已修复",
   "fix": "2026-10-23取得空闲OS锁后持锁重读；29项完成／失败交错、真实中断／错误释放及HTTP／版本选择通过，86原资料不变；见[报告](../archive/reports-2026-10/report-2026-10-23-acceptance-state.md)。未重跑整仓或将其他存储／HTTP问题视为解决",
   "status": "resolved stale-snapshot race; targeted verification only",
   "state": "resolved"
  },
  {
   "id": "TD015",
   "found": "2026-10-24/F000",
   "severity": "medium; verification gate",
   "impact": "2026-10-24已恢复：静态门禁（ruff 43项、format 30文件、mypy 50项，均2026-10-22引入）修复；全量从“20%处无限挂起＋大量失败”恢复为3440 passed／4 failed／3 skipped，其中3项为高负载下TD012既有偶发、单独连跑通过，第4项（前序测试泄漏sqlite连接）已修",
   "fix": "见sprint-verify-gate-restore.md；剩余偶发归TD012",
   "status": "resolved; 2026-10-25 full verify green (3538 passed, 0 failed)",
   "state": "resolved"
  },
  {
   "id": "TD016",
   "found": "2026-10-24/F005",
   "severity": "high; delivered feature regression (fixed)",
   "impact": "2026-10-22合同提交7aad0df后，多录像联合检索hybrid／semantic（含“已有细节”）在保存时被“单任务检索投影缺少embedding”拒绝：`cli/main.py`为渲染候选行临时构造的单任务结果未带联合检索的embedding身份。真实demo复现后已修并实跑成功",
   "fix": "修复见sprint-verify-gate-restore.md",
   "status": "resolved",
   "state": "resolved"
  },
  {
   "id": "TD017",
   "found": "2026-10-25/F006",
   "severity": "low; display only, gate unaffected",
   "impact": "验收就绪摘要（`application/acceptance_readiness.py`）两处只影响显示：①只读最新100个任务、忽略`hasMore`／`total`（第138行附近），项目超过100个任务且唯一已完成任务较旧时会误报“没有可检索的已完成运行”；②`userDecisionsPending`固定写`A_or_B_or_D_coverage_gap`（第192行附近），没有覆盖缺口的项目也显示“长钟馗3个拒绝窗口待决定”，且`test_empty_project_blocked_no_runs`当前断言该行为。关联选项与冻结／关联检查另行构建，验收结论不受影响",
   "fix": "修法：分页读完全部任务或给出“部分快照”提示并显示总数；仅在确有覆盖缺口任务时给出A/B/D待决定并写出具体任务ID（需同步改该测试）。来源：2026-10-25第二轮验收流程审查工作流（P2）",
   "status": "resolved 2026-10-26: readiness reads every task page by default (explicit page → partialSnapshot/unknown_partial_task_snapshot, never \"no searchable run\"); A/B/D decision only when a coverage-gap run exists; UI labels generic; targeted tests pass",
   "state": "resolved"
  },
  {
   "id": "TD018",
   "found": "2026-10-31/P008",
   "severity": "high; disk exhaustion",
   "impact": "变速前置音轨测试在26秒内生成58.29GiB NUT；无落盘限额，失败目录和已集成工作树长期保留。用户未手动删除但活动narration-integration消失，来源未证实",
   "fix": "已释放58.29GiB，FFmpeg -fs/文件动态预算(8MiB–2GiB)/目录4GiB/余量2GiB、退出复核、失败NUT与测试fixture回收通过相关回归及独立限定PASS；两棵已入库工作树已退役。历史未知改动副本逐项核清后退役，活动目录消失继续只读归因，不影响主树与用户素材；见[sprint](sprint-cache-reclamation.md)",
   "status": "resolved: protection delivered; 2026-10-31 all 60 legacy worktrees retired (uncommitted edits kept as snapshot commits on their own branches, duplicate toolchain copies byte-verified before removal); narration-integration was created nested inside narration-mix; 8 small .worktrees stubs remain locked by Codex sandbox ACL for the cache-cleanup owner",
   "state": "resolved"
  },
  {
   "id": "TD019",
   "found": "2026-10-31/P026",
   "severity": "low; narration edge cases",
   "impact": "关键评估P2：①取消请求只在内存，接受取消后、写终态前进程硬退出，新进程可能把已取消旁白提升为completed（毫秒窗口）；②sapi_narration每次读取整读WAV并重复哈希，长旁白使历史列表/版本链变慢；③祖先挂过后又移除的旁白资产被篡改时，后代版本链仍校验失败（与配乐语义一致）",
   "fix": "①取消先原子写cancel-requested标记，get/verify遇标记判interrupted；②改流式hash_file与分块PCM检查；③保持链完整性语义并在创作指南说明",
   "status": "resolved: 2026-11-01 persisted cancel marker honoured on restart promotion, chunked hashing/PCM checks; ancestor chain integrity kept by design",
   "state": "resolved"
  },
  {
   "id": "TD020",
   "found": "2026-11-01/P020",
   "severity": "low; extraction coverage",
   "impact": "活动规则提取为离线句式匹配：未覆盖的写法一律返回“未识别”，必带/可选话题与禁止事项只按关键词判断",
   "fix": "积累真实活动规则样本做回归集；复合时长按分+秒合并；扩展自…起/截止标签/OCR杪→秒/≧；必要时获批后用模型二次核对",
   "status": "resolved: 2026-11-01 corpus ≥60 lines + 自…起/OCR/全角/禁止类句式；未识别不猜；模型二次核对仍需许可故不纳入本债",
   "state": "resolved"
  },
  {
   "id": "TD021",
   "found": "2026-11-01/复审",
   "severity": "low; robustness",
   "impact": "复审剩余：.building-*清理、make-proxy错误分类、知识库 local_files 复用与消失文件容错、xmeml 变速",
   "fix": "清理/CLI/知识库 helper/xmeml timeremap 结构；Premiere 真机导入需有软件时人工",
   "status": "resolved: 2026-11-01 local_files bounded/exclusive + mtime race skip; xmeml timeremap XML (Apple/Premiere dialect) + structure tests; live Premiere import still non-claim",
   "state": "resolved"
  },
  {
   "id": "TD022",
   "found": "2026-11-01/复盘",
   "severity": "medium; red tests on main",
   "impact": "2026-11-01 T23 给渲染器加了 `presentation` 参数，5 个测试文件里的假渲染器没有跟进，导致约 37 个创作/旁白/发布包测试在 main 上失败（产品代码本身无误）",
   "fix": "假渲染器补上 `presentation=None` 并透传",
   "status": "resolved 2026-11-01: fakes updated; test_render_checks_effective_audio_receipt passes without xfail",
   "state": "resolved"
  },
  {
   "id": "TD023",
   "found": "2026-11-01/复盘",
   "severity": "medium; architecture",
   "impact": "T17 窗口级片段缓存让 `application/analysis.py` 直接导入并实例化 `infrastructure.window_segment_cache.WindowSegmentCache`，违反分层（应用层做 I/O）",
   "fix": "纯函数（cache_key/fingerprint/remint_events/digest）移到 application，缓存读写经端口注入；分析靠近付费调用边界，改前要有定向测试",
   "status": "resolved 2026-11-03：纯函数（键、指纹、重铸事件）移到 `application/window_segments.py`，文件缓存经 `AnalysisPorts.segment_cache` 端口注入（CLI 构造，根目录不可用时只关闭复用）；架构测试放行名单清空；新增 `test_window_cache_port_reuses_identical_windows_without_vision_calls`（第二个项目相同窗口零次视觉调用）。",
   "state": "resolved"
  },
  {
   "id": "TD024",
   "found": "2026-11-01/复盘",
   "severity": "high before F006; retrieval regression",
   "impact": "11-01 TD004 离线别名与闸门提交后，`test_retrieval_negation.py` 4 条用例失败：泛描述被整体过滤、仅标签事件不可搜、否认动作挡住其他动作命中、TD010 混合语义金样",
   "fix": "对照 455ea7a..1fcd941 的 retrieval 改动逐条判定是代码回归还是测试过时；修复前不再追加别名闸门",
   "status": "resolved 2026-11-03：逐条判定。① 已否认跳跃、但带 attack 标签的片段搜“攻击”被语义闸门挡掉，属于代码回归，已修：语义闸门对不在“标签滥标名单”里的动作（attack）认可标签证据。② 泛描述（如“打开背包”）搜“跳跃”不再返回，③ 只有 jump 标签的片段不再返回：两条都是 TD004 为精度有意改的（真实素材里 jump/move 等标签标得太宽），测试过时，已按现行设计改写，并补了“只有 attack 标签仍可搜到”的用例。xfail 已移除。",
   "state": "resolved"
  },
  {
   "id": "TD025",
   "found": "2026-11-05/J1",
   "severity": "medium; preview usability",
   "impact": "原单video切镜及转场预览与导出不一致",
   "fix": "2026-11-06工作分支已实现双槽预加载、整数输出帧布局、dissolve/三角源音增益；三速真实媒体与18张导出对照、FFT方向、缓冲/退出及非法布局回归通过；root组合58通过；manifest占用修复后完整verify4874通过/7跳过，已合main。真人设备卡顿和全音轨ducking一致性仍待验",
   "status": "partial: dual-slot dissolve locally verified; full gate passed; local sidechain preview verified 4899/7; broad device/user quality pending",
   "state": "partial"
  },
  {
   "id": "TD026",
   "found": "2026-11-09/真实动态策划",
   "severity": "high; paid-result evidence",
   "impact": "Provider完成后应用验证/编译失败，只留reasoning.failed，未保存parsed output/具体异常，无法离线诊断已付费结果",
   "fix": "指定单次许可已耗用；原失败回执/账本不可改或重发。下一切片在应用验证前用既有不可覆盖文件/receipt保存Provider parsed output并保留受控校验错误，以fake验证旧记录兼容，不能伪造丢失原文；实证见.cache/scratch/j1-dynamic-plan-authorization/outcome.md",
   "status": "resolved: retention shipped (e15e39e) and used 2026-11-09: the authorized send's retained output diagnosed the fingerprint mis-copy offline (fix 1838938); the original 11-09 lost output stays unrecoverable, no retry",
   "state": "resolved"
  },
  {
   "id": "TD027",
   "found": "2026-11-10/P029",
   "severity": "low; receipt verification",
   "impact": "渲染回执校验（creation_jobs verify）不把 receipt.presentation（安全区/角标/字幕样式）与请求重算的 PresentationOptions.receipt() 比对；篡改该字段不会被发现（2026-11-10 字幕样式审查发现，既有缺口）",
   "fix": "verify 时由请求重算 presentation 回执并逐字段比对，旧回执无该键时按无 presentation 处理",
   "status": "resolved: 2026-11-10 verify 由请求重算 presentation 回执比对（字幕样式仅在实际烧入时计入）；注入回执的样式/角标被识别为interrupted",
   "state": "resolved"
  },
  {
   "id": "TD028",
   "found": "2026-11-10/测试",
   "severity": "low; browser test flake",
   "impact": "浏览器测试用 create_server(127.0.0.1, 0) 取随机端口，偶尔拿到 Chromium 禁用端口（如1720）导致 ERR_UNSAFE_PORT 假错误（2026-11-10 单项复跑即过）",
   "fix": "测试服务器取端口时跳过 Chromium 受限端口列表，或固定从安全端口段分配",
   "status": "resolved: 2026-11-10 create_server(port 0) 与桌面宿主 FreePort 均跳过 Chromium 受限端口；本机动态端口段为1024起，真实用户同样可能遇到；回归测试+桌面构建Smoke通过",
   "state": "resolved"
  }
 ],
 "human": [
  {
   "item": "代表性素材与原录制分组",
   "how": "用户已补3游戏／6文件，可用路径已保存；正式准备时复用`/acceptance`登记来源／同源关系和开发／测试用途",
   "when": "仅在正式冻结／代表集确认时需要；当前不催更多文件，不立即付费",
   "state": "新素材可用已完成，分组／独立性未核；原登记3源仍2保守组，不由文件数自动扩组。见material-availability-2026-10-24.md"
  },
  {
   "item": "新来源的事前查询与原片参考",
   "how": "在模型分析／看结果前，在原片步骤记真实区间、reviewer／标签版本，下载记录再提交；只补新增来源／缺例",
   "when": "正式主查询须至少10个不同可用参考事件；旧10样例合计不满足各主查询要求",
   "state": "已有原答案继续复用，不重标。武器菜单展示无已确认样例、另两片空白仍未知；完成以保存／提交记录和冻结计划为证。2026-10-27起新生成的标注页有“x/10还差y个”、已登记区间条、重叠提醒和键盘标记（I／O、逗号／句号、[ ]），见原片标注指南“省力的辅助”"
  },
  {
   "item": "长钟馗3拒绝缺口",
   "how": "A保留缺口、B另立定向补窗新费用提案、D暂缓；C离线改进已完成。只读查看“覆盖缺口 ↗”／`coverage-gap-report`",
   "when": "仅在要改变本片完整资格或新增调用时决策；当前不能作为Completed检索／绑定",
   "state": "A/B/D未代选，B未授权。原v2续跑已经结束；任何补窗不得夹带269成功窗。草稿不是批准"
  },
  {
   "item": "任何新录像分析／补窗费用与图片发送许可",
   "how": "Codex先给明确来源／图片／参数／最高新增费用的具体提案，再由真人批准",
   "when": "真实模型调用前；仅提供路径、继续开发或已有pending预算都不授权",
   "state": "当前无新的具体录像发送批准，另两段仍待分析；完成证据须绑定提案和真实答复"
  },
  {
   "item": "固定候选评分",
   "how": "排名生成后立即提供原片回看及固定前十页，填0–3分／理由／真实事件，再下载提交",
   "when": "正式F006；每个主查询至少7个不同事件可用，缺位／重复计零",
   "state": "尚未触发；不让用户提前评分或补造判断。完成以原排名绑定的实际人评／评分报告为证。2026-10-27起新生成的评分页有中性计数、重复说明、时间重叠提示、回看参考和J/K/P键盘，见候选评审指南“省力的辅助”"
  },
  {
   "item": "v5的28–29秒画面核对",
   "how": "[原画面对照](../../artifacts/detail-json-review-20261011-final/comparison.html)／[可留空记录页](../../artifacts/detail-json-review-20261011-final/review-editor.html)，看蓝发、近景物体和连续判断",
   "when": "用户已答“稍后核对，继续开发”，只影响F009/F010判断，不阻断其他开发",
   "state": "1份真实发布、35–36秒拒绝不开放判断；真人判断仍null，不重复催促，不拿旧反馈确认新结果"
  },
  {
   "item": "分发前第三方许可证确认",
   "how": "看本文顶部 T2 六项及 `licenses/gaps.json`：逐项确认能否随安装包分发，或要求补齐官方 LICENSE",
   "when": "只在对外分发安装包前需要；不阻断开发和本机使用",
   "state": "未确认。TD005 并行哈希提速改由开发方自行决定（暂不做，热缓存已 1.14→0.67 秒），不再占用你的待办"
  },
  {
   "item": "J1 修复后复测（新工作台全流程）",
   "how": "开发完成后再提供复测入口；步骤参考顶部",
   "when": "当前等开发修复；阻断删除旧页面",
   "state": "2026-11-04 第四次反馈已收到，全流程未通过；见 [核查](j1-fourth-trial-audit.md)。第三次初稿评价保留，不当作新增能力验收"
  },
  {
   "item": "正式业务指标口径",
   "how": "正式评测前确认时间误差、负例告警、等待时间和费用核对口径",
   "when": "相应验收指标冻结前",
   "state": "未确定项保持null；已确认零扣费不重复要求，也不把其他unknown代填0"
  },
  {
   "item": "各平台登录后的上传限值（可选）",
   "how": "在你登录的B站/抖音/快手/小红书网页投稿页，看文件大小、时长、标题/简介字数、标签数的提示，告诉agent或在Studio发布页“平台规格”里填写",
   "when": "想让投稿前检查覆盖更多项时；不阻断开发或出包",
   "state": "2026-11-10 公开官方页仅查到快手15分钟/4G、B站10小时，其余为未配置，见 docs/references/platform-limits-sources.md"
  }
 ]
};
