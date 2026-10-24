# Sprint：素材来源盘点与共用画面检测

更新：2026-10-24，Phase 0，main，Claude Code本机会话。主线位置：[当前里程碑](current-status.md)“下一步”第1项（盘点现有素材的真实录制来源与开发／独立测试用途）。无新录像／图片／付费API；不代填人工分组。

## 为什么做

F006要求10–20段代表录像按原录制会话分组，不能用同一PV、剪辑或切片凑数。冻结检查已拒绝“同SHA分到不同组”，但宣传片剪入实机镜头这类**字节不同、画面相同**的情况目前只能靠人眼。用户确认分组时需要具体证据。

## 事前实证（临时脚本，不入库）

- 17个本地MP4均可ffprobe，共约48分钟；新增6个为30–128秒，三个“实机演示”为46–108秒TapTap展示片。
- 2帧／秒、9×8灰度差值哈希（dHash，64位）：同片重编码＋缩放＋调亮的20秒片段被精确找回（偏移−10秒，40/40）。
- 单帧在不同游戏间可碰巧距离≤4，单帧不能作证据；严格“连续3秒”规则漏掉真实共用。
- 同偏移投票有效：代号：Atom文件夹“PV”与“实机”在偏移−10.0秒上105个可比帧25个距离≤10（24%），其余充足样本对≤7%；抽帧目视为同一角色选择画面（姿势有细微时差）。钟馗两片的近似帧对应多个不相关时间点，是重复标题／暗场而非同偏移。小样本（10帧3中）必须经多重比较校正后不显著。

## 合同

文件归属（写者唯一）：新建`src/gamingcreator/domain/footage_overlap.py`、`src/gamingcreator/application/source_inventory.py`、`src/gamingcreator/infrastructure/ffmpeg_signatures.py`、`tests/test_source_inventory.py`、`scripts/inventory-sources.ps1`、`docs/references/source-inventory-guide.md`；在`src/gamingcreator/cli/main.py`只新增一个`inventory-sources`子命令及其处理函数，不改其他命令。主控负责AGENTS.md、本sprint、HANDOFF／progress／assignments／human-inputs、提交。

1. Domain（无I/O）：`difference_hash(pixels, width=9, height=8) -> int`；信息量（像素总体标准差）低于阈值的帧不参与比较；`find_shared_offsets(a, b, ...)`对每个整数采样偏移统计“双方均有信息量的可比帧数n”与“汉明距离≤max_distance的匹配数m”，相邻±1采样偏移合并投票以容忍动画时差；背景匹配率取该对全部偏移的总体匹配率（并设下限，如0.01）；单侧二项尾概率乘以偏移数（Bonferroni），≤alpha（默认1e-6）且n≥min_compared（默认20）才报告。输出按显著性排序、互不重叠的偏移结果：偏移秒、m／n、A与B中首末匹配采样时间、校正后p值。全部参数显式、可序列化。
2. Infrastructure：用`.tools/ffmpeg/bin/ffmpeg.exe`与现有`run_media_process`（参数列表、取消／超时、输出上限）输出`fps=2,scale=9:8:flags=area,format=gray`的rawvideo；采样时间=序号/fps相对首个视频帧，记为近似秒并写明采样间隔，不声称逐帧PTS精度。不写入素材目录。
3. Application：输入显式文件或目录（目录递归*.mp4，排序固定）；每个来源用现有`FfmpegMediaProcessor.probe`（时长来自流时钟，不用format.duration）与SHA256；两两比较；报告schema `source-inventory-v1`：参数、ffmpeg版本、每来源（路径、字节、sha256、时长微秒、视频编码／尺寸／帧率、采样帧数、有信息量帧数）、同SHA重复组、`sharedFootageCandidates`、`limitations`（固定文案：匹配是共用画面证据；未匹配不证明独立；裁切／黑边／镜像／大面积叠字／变速可漏检；不自动分配录制组，也不改变冻结计划）。`humanDecisionRequired: true`。不分配或建议recordingGroup值。
4. CLI／脚本：`inventory-sources --input <路径...> --output <json>`，输出先写临时文件再原子替换；控制台打印简短中文摘要。PowerShell包装沿用`prepare-benchmark-references.ps1`风格（env.ps1、UTF-8、仓库根）。
5. 测试只用合成lavfi视频（如testsrc2与mandelbrot／不同图案）：派生片=原片截取＋前加3秒其他画面＋缩放＋重编码，须报告约−3秒偏移；无关片不报告；纯色片全部低信息量不报告；同字节副本进入SHA重复组；domain层用构造哈希序列测阈值、校正与相邻偏移合并、非重叠选择。不读GameVideos／artifacts，不调用付费Provider。

## 验收

定向`tests/test_source_inventory.py`与`tests/test_architecture.py`通过；新文件Ruff格式／检查、mypy通过；主控在本机17个素材上实际运行一次，Atom PV／实机须被报告、其余不应出现大量误报，结果保存在ignored artifacts并在本sprint记录。独立评估由gc-reviewer（只读）执行。

## 结果

- 实现（gc-coder角色，general-purpose回退，请求sonnet；运行转录70条回复为claude-sonnet-5-5）：domain `footage_overlap.py`（dHash、显著性、相邻偏移合并、静止画面保护、最密集连续段、同对重叠去重），infrastructure `ffmpeg_signatures.py`（rawvideo提取、ffprobe编码／尺寸／帧率、签名身份），application `source_inventory.py`（报告`source-inventory-v1`，含`notComparable`／`failedSources`），CLI `inventory-sources`，脚本与[指南](../references/source-inventory-guide.md)。
- 首轮真实运行把Slam Tank黑底标题卡与奇迹暖暖“叠纸游戏出品”白底logo卡误报（主控抽帧确认），并重复报告同一段；已加“至少3种不同画面内容”保护与同对范围去重。
- 独立评估gc-reviewer（请求sonnet，只读）：PASS；6项非阻断，其中范围被偶然命中拉长、票数被写成帧数、无效画面来源未提示、单文件失败中止全部、参数重复定义5项已修，测试补齐。未修低优先：min_compared门本身无独立测试、显式文件输入时兄弟子目录输出未拒、提取器溢出／超时路径无测试、跨136对未做族错误率校正（alpha1e-6下约1e-4）、小时级长片对未测耗时。
- 验证：`tests/test_source_inventory.py`＋`test_architecture.py`＋`test_cli.py`共52项全部通过；新文件Ruff格式／检查与mypy通过。本机17素材实跑约73秒：仅报告Atom PV／实机（+10.0秒，49／312票，A方17个不同采样，最密集段PV52.0–64.5对实机42.0–54.0秒，共5段），Atom录音0/552有效画面列入不可比较，无失败。结论见[素材盘点结果](source-inventory-2026-10-24.md)。
- 同轮发现main既有检查门禁失败（与本工具无关）：`ruff check src tests`43项、`ruff format --check`30文件、`mypy`4文件50项，均来自2026-10-22提交，登记TD015另行处理。
