# Sprint：素材盘点识别黑边与镜像（source-inventory-v2）

更新：2026-10-24，Phase 0，main，Claude Code本机会话。主线：F006来源独立性（[盘点](sprint-source-footage-overlap.md)→[冻结强制核对](sprint-freeze-source-inventory.md)之后的召回增强）。无新录像／图片／付费API，不分配录制组。

## 为什么做

盘点已成为benchmark-freeze-v2的阻断依据，但两类常见同源改编会漏检：①加黑边或宽银幕裁切（本仓库钟馗两片为1920×800；同源16:9加黑边版本缩成9×8后指纹完全不同）；②左右镜像后剪入宣传片。漏检会让同源素材被当作“无证据”而进入不同录制组。

## 合同

文件归属（单一写者）：`src/gamingcreator/domain/footage_overlap.py`、`src/gamingcreator/infrastructure/ffmpeg_signatures.py`、`src/gamingcreator/application/source_inventory.py`、`src/gamingcreator/application/benchmark_inventory_binding.py`、`tests/test_source_inventory.py`、`tests/test_benchmark_inventory_binding.py`、`docs/references/source-inventory-guide.md`。主控负责sprint／HANDOFF／progress／assignments与提交。

1. 黑边：每个来源先用项目ffmpeg的`cropdetect`（固定参数，如`fps=1,cropdetect=limit=24:round=2:reset=0`）得到稳定裁切框；仅当裁切去掉的是边缘均匀暗区且剩余面积≥原画面40%时采用，否则不裁。签名滤镜变为`crop=W:H:X:Y,fps=2,scale=9:8:flags=area,format=gray`（不裁时与v1相同）。裁切框写入每个来源的报告（`crop: {width,height,x,y}`或null）。
2. 镜像：提取时由同一像素缓冲额外计算逐行反转后的dHash（无需二次解码）；比较时对每对来源执行A正常对B正常、A正常对B镜像两次检测，候选增加`mirrored: true|false`；同一对两种结果按显著性合并并去重（沿用范围重叠去重）。Domain保持无I/O。
3. 报告`schemaVersion`升为`source-inventory-v2`：每个来源增加`crop`，候选增加`mirrored`，`parameters`记录cropdetect参数与镜像开关；`limitations`在原文基础上更新为“裁切（非均匀黑边）／大面积叠字／变速及很短低动作镜头仍可能漏检”，并保留“匹配是证据、未匹配不证明独立、不分配录制组”。
4. `benchmark_inventory_binding`严格解析同时接受v1（原字段集与原`LIMITATIONS_V1`文案，今天已生成的报告继续有效）与v2（新字段集与新文案）；派生`sourceInventory`对v2共用画面对记录`mirrored`。已存v2冻结（若有）与v1冻结字节不变。
5. 测试只用合成lavfi视频：原片派生①pad加黑边＋重编码、②hflip镜像＋重编码，均须报告且偏移正确（②`mirrored=true`）；无关片不报告；无黑边素材`crop`为null且签名与v1一致；绑定层v1与v2报告都能冻结、篡改仍拒绝。

## 验收

定向`test_source_inventory.py`、`test_benchmark_inventory_binding.py`、`test_benchmark_preparation.py`、`test_architecture.py`通过（-W error），ruff／mypy全仓干净；主控在本机17素材重跑盘点：仍报告Atom PV／实机，无新增大量误报，记录各来源crop结果与耗时；用新报告重做Atom异组反例冻结仍被拦。独立评估gc-reviewer。

## 结果

- 实现：gc-coder（请求sonnet）；评估：gc-reviewer（请求sonnet，只读）PASS，两处变异（删40%面积判断、翻转镜像优先级）均被测试发现；低严重度发现（正反两向分别校正、对称画面镜像标签偏差、闪白／部分黑边不裁只漏检、旋转视频视为不裁、多一次ffprobe）已写入指南限制，不改代码。
- 新增决定：`minCropRemovedFraction=0.02`（去除不到2%宽高的框忽略，避免暗角改变v1签名），记录于报告参数。
- 真实验证：钟馗6分钟片段加黑边（pad到1920×1080）与心动小镇实机片段镜像，HEAD版本0候选，新版本分别在−100秒、−30秒（镜像）报告；17素材重跑129秒（原73秒），仍仅Atom PV／实机，自动裁边2个（奇迹暖暖宣传片1920×818、苍翼实机2560×1144）；新`report-v2.json`与原v1`report.json`冻结Atom异组反例均得到`shared_footage_has_different_recording_groups`；5个已存冻结读取与SHA不变。
- 验证：定向7文件214项通过（-W error），ruff／mypy全仓干净。完整verify未重跑。
